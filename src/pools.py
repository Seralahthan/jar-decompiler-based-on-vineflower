"""
Bounded thread-pool executors for decompilation jobs.

Two separate pools prevent heavy full-JAR decompilations (-Xmx2g each)
from starving lightweight per-class requests (-Xmx256m each).

A semaphore wraps the full-decompile pool so that callers get an
immediate 503 when the queue is saturated, rather than silently
building up an unbounded backlog.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

from config import (
    FULL_DECOMPILE_POOL_SIZE,
    CLASS_DECOMPILE_POOL_SIZE,
    FULL_DECOMPILE_QUEUE_LIMIT,
)


class QueueFullError(Exception):
    """Raised when the decompilation queue is saturated."""


# ---------------------------------------------------------------------------
# Full JAR decompile + indexing  (both spawn JVMs with -Xmx2g)
# ---------------------------------------------------------------------------
_full_pool = ThreadPoolExecutor(
    max_workers=FULL_DECOMPILE_POOL_SIZE,
    thread_name_prefix="full-decompile",
)
_full_semaphore = threading.Semaphore(FULL_DECOMPILE_QUEUE_LIMIT)


def submit_full_decompile(fn, *args):
    """Submit a full-JAR decompile or indexing job.

    Raises ``QueueFullError`` when the queue depth exceeds the limit.
    """
    if not _full_semaphore.acquire(blocking=False):
        raise QueueFullError("Server busy — too many decompilation jobs queued. Please try again shortly.")

    def _wrapper(*a):
        try:
            return fn(*a)
        finally:
            _full_semaphore.release()

    return _full_pool.submit(_wrapper, *args)


# ---------------------------------------------------------------------------
# Per-class decompile  (spawns JVMs with -Xmx256m)
# ---------------------------------------------------------------------------
_class_pool = ThreadPoolExecutor(
    max_workers=CLASS_DECOMPILE_POOL_SIZE,
    thread_name_prefix="class-decompile",
)


def submit_class_decompile(fn, *args, timeout=30):
    """Submit a per-class decompile and block until the result is ready.

    Returns the decompiled source string.
    Raises ``TimeoutError`` if the job does not complete within *timeout* seconds.
    """
    future = _class_pool.submit(fn, *args)
    return future.result(timeout=timeout)
