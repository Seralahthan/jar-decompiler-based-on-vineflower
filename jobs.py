"""
Redis-backed job store.

Each job is stored as a Redis hash  ``job:<job_id>``  with scalar fields.
Large blobs (class cache, method index) get their own keys so they can be
read/written independently without serialising the entire job every time.

A thin process-local dict holds ``threading.Lock`` objects that cannot live
in Redis — these protect per-class decompilation within a single Gunicorn
worker.  Cross-worker duplication is harmless (result is deterministic and
the Redis cache write is idempotent).
"""

import json
import shutil
import threading
import time

import redis

from config import REDIS_URL, JOB_TTL_SECONDS, UPLOAD_DIR, OUTPUT_DIR

# ---------------------------------------------------------------------------
# Redis connection
# ---------------------------------------------------------------------------
_redis = redis.from_url(REDIS_URL, decode_responses=True)

# ---------------------------------------------------------------------------
# Process-local class locks (cannot be stored in Redis)
# ---------------------------------------------------------------------------
_class_locks: dict[str, threading.Lock] = {}
_class_locks_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def _job_key(job_id: str) -> str:
    return f"job:{job_id}"


def _cache_key(job_id: str) -> str:
    return f"job:{job_id}:class_cache"


def _index_key(job_id: str) -> str:
    return f"job:{job_id}:method_index"


# ---------------------------------------------------------------------------
# Job CRUD
# ---------------------------------------------------------------------------

def create_job(job_id: str, jar_path: str, created_at: float) -> None:
    key = _job_key(job_id)
    _redis.hset(key, mapping={
        "status": "queued",
        "message": "Queued for decompilation\u2026",
        "progress": "0",
        "created_at": str(created_at),
        "jar_path": str(jar_path),
    })
    _redis.expire(key, JOB_TTL_SECONDS)


def get_job(job_id: str) -> dict | None:
    data = _redis.hgetall(_job_key(job_id))
    return data if data else None


def update_job(job_id: str, **fields) -> None:
    str_fields = {k: str(v) for k, v in fields.items()}
    key = _job_key(job_id)
    _redis.hset(key, mapping=str_fields)
    _redis.expire(key, JOB_TTL_SECONDS)


# ---------------------------------------------------------------------------
# Class cache  (decompiled source per class path)
# ---------------------------------------------------------------------------

def get_class_cache(job_id: str, class_path: str) -> str | None:
    return _redis.hget(_cache_key(job_id), class_path)


def set_class_cache(job_id: str, class_path: str, source: str) -> None:
    key = _cache_key(job_id)
    _redis.hset(key, class_path, source)
    _redis.expire(key, JOB_TTL_SECONDS)


# ---------------------------------------------------------------------------
# Class lock  (process-local)
# ---------------------------------------------------------------------------

def get_class_lock(job_id: str) -> threading.Lock:
    with _class_locks_lock:
        if job_id not in _class_locks:
            _class_locks[job_id] = threading.Lock()
        return _class_locks[job_id]


# ---------------------------------------------------------------------------
# Method index
# ---------------------------------------------------------------------------

def set_method_index(job_id: str, index: dict) -> None:
    key = _index_key(job_id)
    _redis.set(key, json.dumps(index))
    _redis.expire(key, JOB_TTL_SECONDS)


def get_method_index(job_id: str) -> dict:
    raw = _redis.get(_index_key(job_id))
    return json.loads(raw) if raw else {}


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def delete_job_artifacts(job_id: str) -> None:
    """Remove filesystem artifacts and Redis keys for a job."""
    upload_path = UPLOAD_DIR / job_id
    output_path = OUTPUT_DIR / job_id
    index_path = OUTPUT_DIR / f"{job_id}_index"
    result_zip = OUTPUT_DIR / f"{job_id}.zip"

    for p in (upload_path, output_path, index_path):
        shutil.rmtree(p, ignore_errors=True)
    result_zip.unlink(missing_ok=True)

    _redis.delete(_job_key(job_id), _cache_key(job_id), _index_key(job_id))

    with _class_locks_lock:
        _class_locks.pop(job_id, None)


def get_expired_job_ids() -> list[str]:
    """Return job IDs whose created_at is older than JOB_TTL_SECONDS.

    Redis TTL handles key expiry, but filesystem artifacts still need
    explicit cleanup.  This scans all ``job:*`` hashes that are still
    alive and checks the ``created_at`` field.
    """
    now = time.time()
    expired: list[str] = []
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
    return expired
