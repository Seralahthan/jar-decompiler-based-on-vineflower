"""Gunicorn configuration for production deployment."""

import os
import threading

# ---------------------------------------------------------------------------
# Server socket
# ---------------------------------------------------------------------------
bind = f"127.0.0.1:{os.environ.get('HOST_PORT', '9090')}"

# ---------------------------------------------------------------------------
# Worker processes
# ---------------------------------------------------------------------------
workers = int(os.environ.get("GUNICORN_WORKERS", "4"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"  # threaded workers for blocking I/O + thread pools

# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------
timeout = 120          # per-class decompile can take up to 30s; give headroom
graceful_timeout = 30  # time for in-flight requests to finish on shutdown
keepalive = 5

# ---------------------------------------------------------------------------
# Worker lifecycle
# ---------------------------------------------------------------------------
max_requests = 1000       # restart workers periodically to reclaim memory
max_requests_jitter = 50  # stagger restarts across workers

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
accesslog = "-"
errorlog = "-"
loglevel = "info"
# Format: include worker PID and thread name for debugging multi-worker issues.
# %(p)s = worker PID, %({X-Thread}e)s = thread name injected via WSGI middleware.
access_log_format = '[worker:%(p)s/%({X-Thread}e)s] %(h)s "%(r)s" %(s)s %(b)s'


def post_fork(server, worker):
    """Start the cleanup daemon thread in each worker process."""
    from services.cleanup import cleanup_old_jobs

    t = threading.Thread(target=cleanup_old_jobs, daemon=True)
    t.start()
