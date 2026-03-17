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
JOB_TTL_SECONDS = 3600  # 1 hour

# ---------------------------------------------------------------------------
# Thread pool sizes (per Gunicorn worker process)
# ---------------------------------------------------------------------------
# Full JAR decompile + indexing both spawn JVMs with -Xmx2g
FULL_DECOMPILE_POOL_SIZE = int(os.environ.get("FULL_DECOMPILE_POOL_SIZE", "4"))
# Per-class decompile uses -Xmx256m per JVM
CLASS_DECOMPILE_POOL_SIZE = int(os.environ.get("CLASS_DECOMPILE_POOL_SIZE", "20"))
# Maximum queued full-decompile jobs before returning 503
FULL_DECOMPILE_QUEUE_LIMIT = FULL_DECOMPILE_POOL_SIZE * 2
