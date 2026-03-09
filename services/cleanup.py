import time

from jobs import jobs, jobs_lock, delete_job_artifacts


def cleanup_old_jobs():
    """Daemon thread: remove job artifacts older than 1 hour, every 5 minutes."""
    while True:
        time.sleep(300)
        now = time.time()
        with jobs_lock:
            expired = [
                jid for jid, job in jobs.items()
                if now - job.get("created_at", now) > 3600
            ]
        for jid in expired:
            delete_job_artifacts(jid)
            with jobs_lock:
                jobs.pop(jid, None)
