import shutil
import threading
from pathlib import Path

from config import UPLOAD_DIR, OUTPUT_DIR

# In-memory job store: job_id -> {status, message, progress, ...}
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def delete_job_artifacts(job_id: str):
    upload_path = UPLOAD_DIR / job_id
    output_path = OUTPUT_DIR / job_id
    index_path  = OUTPUT_DIR / f"{job_id}_index"
    result_zip  = OUTPUT_DIR / f"{job_id}.zip"
    for p in (upload_path, output_path, index_path):
        shutil.rmtree(p, ignore_errors=True)
    result_zip.unlink(missing_ok=True)
