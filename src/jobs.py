"""
Job store with automatic Redis/in-memory selection.

When Redis is reachable (production, Docker) the store is Redis-backed so
that multiple Gunicorn workers and future multi-pod deployments share state.

When Redis is *not* reachable (local ``./run.sh`` without a Redis server)
the store falls back transparently to a plain in-memory dict + threading
lock — exactly like the original implementation.

Class cache and method index are keyed by JAR SHA-256 hash (not job ID)
so that multiple uploads of the same JAR share decompiled results.
"""

import json
import logging
import shutil
import threading
import time

from config import REDIS_URL, JOB_TTL_SECONDS, UPLOAD_DIR, OUTPUT_DIR

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try to connect to Redis; fall back to in-memory if unavailable
# ---------------------------------------------------------------------------
_redis = None
try:
    import redis as _redis_lib
    _candidate = _redis_lib.from_url(REDIS_URL, decode_responses=True)
    _candidate.ping()
    _redis = _candidate
    log.info("Job store: Redis (%s)", REDIS_URL)
except Exception:
    log.info("Job store: in-memory (Redis unavailable at %s)", REDIS_URL)

# ---------------------------------------------------------------------------
# Process-local class locks (cannot be stored in Redis)
# ---------------------------------------------------------------------------
_class_locks: dict[str, threading.Lock] = {}
_class_locks_lock = threading.Lock()

# ---------------------------------------------------------------------------
# In-memory fallback store
# ---------------------------------------------------------------------------
_mem_jobs: dict[str, dict] = {}
_mem_lock = threading.Lock()
_mem_class_cache: dict[str, dict[str, str]] = {}    # jar_hash -> {class_path: source}
_mem_method_index: dict[str, dict] = {}              # jar_hash -> {method: [locations]}


# ═══════════════════════════════════════════════════════════════════════════
# Key helpers (Redis mode)
# ═══════════════════════════════════════════════════════════════════════════

def _job_key(job_id: str) -> str:
    return f"job:{job_id}"


def _cache_key(jar_hash: str) -> str:
    return f"cache:{jar_hash}"


def _index_key(jar_hash: str) -> str:
    return f"index:{jar_hash}"


# Cache entries live longer than per-job data since they benefit
# any future upload of the same JAR.
_CACHE_TTL = JOB_TTL_SECONDS * 2  # 8 hours


# ═══════════════════════════════════════════════════════════════════════════
# Job CRUD
# ═══════════════════════════════════════════════════════════════════════════

def create_job(job_id: str, jar_path: str, created_at: float,
               jar_hash: str = "") -> None:
    fields = {
        "status": "queued",
        "message": "Queued for decompilation\u2026",
        "progress": "0",
        "created_at": str(created_at),
        "jar_path": str(jar_path),
        "jar_hash": jar_hash,
    }
    if _redis:
        key = _job_key(job_id)
        _redis.hset(key, mapping=fields)
        _redis.expire(key, JOB_TTL_SECONDS)
    else:
        with _mem_lock:
            _mem_jobs[job_id] = fields


def get_job(job_id: str) -> dict | None:
    if _redis:
        data = _redis.hgetall(_job_key(job_id))
        return data if data else None
    else:
        with _mem_lock:
            job = _mem_jobs.get(job_id)
            return dict(job) if job else None


def update_job(job_id: str, **fields) -> None:
    str_fields = {k: str(v) for k, v in fields.items()}
    if _redis:
        key = _job_key(job_id)
        _redis.hset(key, mapping=str_fields)
        _redis.expire(key, JOB_TTL_SECONDS)
    else:
        with _mem_lock:
            if job_id in _mem_jobs:
                _mem_jobs[job_id].update(str_fields)


# ═══════════════════════════════════════════════════════════════════════════
# Class cache  (keyed by JAR hash for content-based deduplication)
# ═══════════════════════════════════════════════════════════════════════════

def get_class_cache(jar_hash: str, class_path: str) -> str | None:
    if not jar_hash:
        return None
    if _redis:
        return _redis.hget(_cache_key(jar_hash), class_path)
    else:
        with _mem_lock:
            return _mem_class_cache.get(jar_hash, {}).get(class_path)


def set_class_cache(jar_hash: str, class_path: str, source: str) -> None:
    if not jar_hash:
        return
    if _redis:
        key = _cache_key(jar_hash)
        _redis.hset(key, class_path, source)
        _redis.expire(key, _CACHE_TTL)
    else:
        with _mem_lock:
            _mem_class_cache.setdefault(jar_hash, {})[class_path] = source


# ═══════════════════════════════════════════════════════════════════════════
# Class lock  (process-local fallback for in-memory mode)
# ═══════════════════════════════════════════════════════════════════════════

def get_class_lock(jar_hash: str) -> threading.Lock:
    """Return a process-local lock. Keyed by jar_hash so that concurrent
    requests for the same JAR content share the lock."""
    key = jar_hash or "default"
    with _class_locks_lock:
        if key not in _class_locks:
            _class_locks[key] = threading.Lock()
        return _class_locks[key]


# ═══════════════════════════════════════════════════════════════════════════
# Distributed class lock  (Redis-backed, cross-worker / cross-pod)
# ═══════════════════════════════════════════════════════════════════════════

_CLASS_LOCK_TTL = 60  # auto-expire after 60s to prevent deadlocks


def acquire_class_lock(jar_hash: str, class_path: str) -> bool:
    """Try to acquire a distributed lock for decompiling a specific class.

    Keyed by JAR hash so the lock deduplicates across different jobs that
    uploaded the same JAR content.

    Returns True if the lock was acquired (caller should decompile),
    or False if another worker already holds it (caller should poll cache).
    """
    if not _redis or not jar_hash:
        return True  # in-memory mode uses process-local locks instead
    lock_key = f"lock:{jar_hash}:{class_path}"
    return bool(_redis.set(lock_key, "1", nx=True, ex=_CLASS_LOCK_TTL))


def release_class_lock(jar_hash: str, class_path: str) -> None:
    """Release the distributed lock after decompilation completes."""
    if not _redis or not jar_hash:
        return
    lock_key = f"lock:{jar_hash}:{class_path}"
    _redis.delete(lock_key)


def wait_for_class_cache(jar_hash: str, class_path: str,
                         timeout: float = 35, interval: float = 0.3) -> str | None:
    """Poll cache until the class source appears or timeout is reached.

    Used when another worker holds the distributed lock — instead of
    decompiling again, we wait for the result to appear in cache.
    """
    if not jar_hash:
        return None
    deadline = time.time() + timeout
    while time.time() < deadline:
        cached = get_class_cache(jar_hash, class_path)
        if cached is not None:
            return cached
        time.sleep(interval)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Method index  (keyed by JAR hash for content-based deduplication)
# ═══════════════════════════════════════════════════════════════════════════

def set_method_index(jar_hash: str, index: dict) -> None:
    if not jar_hash:
        return
    if _redis:
        key = _index_key(jar_hash)
        _redis.set(key, json.dumps(index))
        _redis.expire(key, _CACHE_TTL)
    else:
        with _mem_lock:
            _mem_method_index[jar_hash] = index


def get_method_index(jar_hash: str) -> dict:
    if not jar_hash:
        return {}
    if _redis:
        raw = _redis.get(_index_key(jar_hash))
        return json.loads(raw) if raw else {}
    else:
        with _mem_lock:
            return _mem_method_index.get(jar_hash, {})


# ═══════════════════════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════════════════════

def delete_job_artifacts(job_id: str) -> None:
    """Remove filesystem artifacts and job store entry.

    Note: global cache (class cache, method index) is NOT deleted here
    because it is shared across jobs and managed by its own TTL.
    """
    upload_path = UPLOAD_DIR / job_id
    output_path = OUTPUT_DIR / job_id
    index_path = OUTPUT_DIR / f"{job_id}_index"
    result_zip = OUTPUT_DIR / f"{job_id}.zip"

    for p in (upload_path, output_path, index_path):
        shutil.rmtree(p, ignore_errors=True)
    result_zip.unlink(missing_ok=True)

    if _redis:
        _redis.delete(_job_key(job_id))
    else:
        with _mem_lock:
            _mem_jobs.pop(job_id, None)

    with _class_locks_lock:
        _class_locks.pop(job_id, None)


def get_expired_job_ids() -> list[str]:
    """Return job IDs whose created_at is older than JOB_TTL_SECONDS."""
    now = time.time()
    expired: list[str] = []

    if _redis:
        cursor = "0"
        while True:
            cursor, keys = _redis.scan(cursor=cursor, match="job:*", count=100)
            for key in keys:
                # Skip non-job keys
                if key.count(":") > 1:
                    continue
                created = _redis.hget(key, "created_at")
                if created and now - float(created) > JOB_TTL_SECONDS:
                    job_id = key.split(":", 1)[1]
                    expired.append(job_id)
            if cursor == 0 or cursor == "0":
                break
    else:
        with _mem_lock:
            for job_id, job in _mem_jobs.items():
                created = job.get("created_at")
                if created and now - float(created) > JOB_TTL_SECONDS:
                    expired.append(job_id)

    return expired
