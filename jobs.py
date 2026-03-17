"""
Job store with automatic Redis/in-memory selection.

When Redis is reachable (production, Docker) the store is Redis-backed so
that multiple Gunicorn workers and future multi-pod deployments share state.

When Redis is *not* reachable (local ``./run.sh`` without a Redis server)
the store falls back transparently to a plain in-memory dict + threading
lock — exactly like the original implementation.
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
_mem_class_cache: dict[str, dict[str, str]] = {}   # job_id -> {class_path: source}
_mem_method_index: dict[str, dict] = {}             # job_id -> {method: [locations]}


# ═══════════════════════════════════════════════════════════════════════════
# Key helpers (Redis mode)
# ═══════════════════════════════════════════════════════════════════════════

def _job_key(job_id: str) -> str:
    return f"job:{job_id}"


def _cache_key(job_id: str) -> str:
    return f"job:{job_id}:class_cache"


def _index_key(job_id: str) -> str:
    return f"job:{job_id}:method_index"


# ═══════════════════════════════════════════════════════════════════════════
# Job CRUD
# ═══════════════════════════════════════════════════════════════════════════

def create_job(job_id: str, jar_path: str, created_at: float) -> None:
    if _redis:
        key = _job_key(job_id)
        _redis.hset(key, mapping={
            "status": "queued",
            "message": "Queued for decompilation\u2026",
            "progress": "0",
            "created_at": str(created_at),
            "jar_path": str(jar_path),
        })
        _redis.expire(key, JOB_TTL_SECONDS)
    else:
        with _mem_lock:
            _mem_jobs[job_id] = {
                "status": "queued",
                "message": "Queued for decompilation\u2026",
                "progress": "0",
                "created_at": str(created_at),
                "jar_path": str(jar_path),
            }


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
# Class cache  (decompiled source per class path)
# ═══════════════════════════════════════════════════════════════════════════

def get_class_cache(job_id: str, class_path: str) -> str | None:
    if _redis:
        return _redis.hget(_cache_key(job_id), class_path)
    else:
        with _mem_lock:
            return _mem_class_cache.get(job_id, {}).get(class_path)


def set_class_cache(job_id: str, class_path: str, source: str) -> None:
    if _redis:
        key = _cache_key(job_id)
        _redis.hset(key, class_path, source)
        _redis.expire(key, JOB_TTL_SECONDS)
    else:
        with _mem_lock:
            _mem_class_cache.setdefault(job_id, {})[class_path] = source


# ═══════════════════════════════════════════════════════════════════════════
# Class lock  (always process-local)
# ═══════════════════════════════════════════════════════════════════════════

def get_class_lock(job_id: str) -> threading.Lock:
    with _class_locks_lock:
        if job_id not in _class_locks:
            _class_locks[job_id] = threading.Lock()
        return _class_locks[job_id]


# ═══════════════════════════════════════════════════════════════════════════
# Method index
# ═══════════════════════════════════════════════════════════════════════════

def set_method_index(job_id: str, index: dict) -> None:
    if _redis:
        key = _index_key(job_id)
        _redis.set(key, json.dumps(index))
        _redis.expire(key, JOB_TTL_SECONDS)
    else:
        with _mem_lock:
            _mem_method_index[job_id] = index


def get_method_index(job_id: str) -> dict:
    if _redis:
        raw = _redis.get(_index_key(job_id))
        return json.loads(raw) if raw else {}
    else:
        with _mem_lock:
            return _mem_method_index.get(job_id, {})


# ═══════════════════════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════════════════════

def delete_job_artifacts(job_id: str) -> None:
    """Remove filesystem artifacts and store entries for a job."""
    upload_path = UPLOAD_DIR / job_id
    output_path = OUTPUT_DIR / job_id
    index_path = OUTPUT_DIR / f"{job_id}_index"
    result_zip = OUTPUT_DIR / f"{job_id}.zip"

    for p in (upload_path, output_path, index_path):
        shutil.rmtree(p, ignore_errors=True)
    result_zip.unlink(missing_ok=True)

    if _redis:
        _redis.delete(_job_key(job_id), _cache_key(job_id), _index_key(job_id))
    else:
        with _mem_lock:
            _mem_jobs.pop(job_id, None)
            _mem_class_cache.pop(job_id, None)
            _mem_method_index.pop(job_id, None)

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
                # Skip sub-keys (class_cache, method_index)
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
