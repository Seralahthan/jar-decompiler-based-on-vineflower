import time

import jobs


def cleanup_old_jobs():
    """Daemon thread: remove job artifacts older than 1 hour, every 5 minutes.

    Redis TTL handles key expiry automatically, but filesystem artifacts
    (uploaded JARs, decompiled output) still need explicit cleanup.
    """
    while True:
        time.sleep(300)
        try:
            expired = jobs.get_expired_job_ids()
            for jid in expired:
                jobs.delete_job_artifacts(jid)
        except Exception:
            pass  # Redis may be temporarily unreachable; retry next cycle
