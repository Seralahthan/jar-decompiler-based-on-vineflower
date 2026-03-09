from pathlib import Path

BASE_DIR = Path(__file__).parent
LIB_DIR = BASE_DIR / "lib"
VINEFLOWER_JAR = LIB_DIR / "vineflower.jar"
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"

MAX_UPLOAD_MB = 200

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
