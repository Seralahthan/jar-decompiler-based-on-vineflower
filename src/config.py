import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
LIB_DIR = BASE_DIR / "lib"
VINEFLOWER_JAR = LIB_DIR / "vineflower.jar"
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"

MAX_UPLOAD_MB = 200

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
JOB_TTL_SECONDS = 14400  # 4 hours

# ---------------------------------------------------------------------------
# Gunicorn
# ---------------------------------------------------------------------------
GUNICORN_WORKERS = int(os.environ.get("GUNICORN_WORKERS", "4"))

# ---------------------------------------------------------------------------
# Thread pool sizes (per Gunicorn worker process)
#
# These are divided by the worker count so that the TOTAL across all workers
# stays within the pod's memory budget.
#
# Pod memory budget for JVMs:
#   Full decompile:  FULL_DECOMPILE_POOL_TOTAL × 2GB
#   Per-class:       CLASS_DECOMPILE_POOL_TOTAL × 256MB
#
# Example with defaults (4 workers, 6GB pod):
#   Full pool:  total=2, per-worker=max(1, 2//4)=1  → 4 workers × 1 = 4 JVMs × 2GB = 8GB peak
#   Class pool: total=8, per-worker=max(1, 8//4)=2  → 4 workers × 2 = 8 JVMs × 256MB = 2GB peak
#   Realistic peak (not all saturated): ~4-5GB
# ---------------------------------------------------------------------------
FULL_DECOMPILE_POOL_TOTAL = int(os.environ.get("FULL_DECOMPILE_POOL_TOTAL", "2"))
CLASS_DECOMPILE_POOL_TOTAL = int(os.environ.get("CLASS_DECOMPILE_POOL_TOTAL", "8"))

FULL_DECOMPILE_POOL_SIZE = max(1, FULL_DECOMPILE_POOL_TOTAL // GUNICORN_WORKERS)
CLASS_DECOMPILE_POOL_SIZE = max(1, CLASS_DECOMPILE_POOL_TOTAL // GUNICORN_WORKERS)

# Maximum queued full-decompile jobs before returning 503
FULL_DECOMPILE_QUEUE_LIMIT = FULL_DECOMPILE_POOL_TOTAL * 2
