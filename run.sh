#!/usr/bin/env bash
# ────────────────────────────────────────────────────────
# run.sh  –  Start the JAR Decompiler web app
# ────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Check Java ──────────────────────────────────────────
if ! command -v java &>/dev/null; then
  echo "ERROR: 'java' not found on PATH."
  echo "Please install Java 11+ (e.g. via Homebrew: brew install openjdk)"
  exit 1
fi
echo "Using Java: $(java -version 2>&1 | head -1)"

# ── Python virtual env ──────────────────────────────────
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating Python virtual environment…"
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "Installing/verifying Python dependencies…"
python3 -m pip install -q -r requirements.txt

# ── Open browser after a short delay ────────────────────
(sleep 2 && open "http://127.0.0.1:9090") &

# ── Start Gunicorn ─────────────────────────────────────
echo ""
echo "  ┌──────────────────────────────────────────┐"
echo "  │   JAR Decompiler is running (Gunicorn)   │"
echo "  │   Open: http://127.0.0.1:9090            │"
echo "  │   Press Ctrl+C to stop                   │"
echo "  └──────────────────────────────────────────┘"
echo ""

# ── Detect Redis ─────────────────────────────────────────
# Without Redis the job store is in-memory (per-process), so
# multiple workers lose track of each other's jobs. Default
# to 1 worker unless Redis is available or the user overrides.
REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"

if command -v redis-cli &>/dev/null && redis-cli -u "$REDIS_URL" ping &>/dev/null; then
  WORKERS="${GUNICORN_WORKERS:-4}"
  echo "  Redis detected — using $WORKERS workers"
else
  WORKERS="${GUNICORN_WORKERS:-1}"
  if [ "$WORKERS" -gt 1 ]; then
    echo "  WARNING: Running $WORKERS workers without Redis."
    echo "  Job state is NOT shared between workers. Install and"
    echo "  start Redis, or set GUNICORN_WORKERS=1 to avoid issues."
  else
    echo "  No Redis — using 1 worker (set GUNICORN_WORKERS to override)"
  fi
fi

# Gunicorn runs from src/ so that imports (config, jobs, routes, etc.) resolve.
# Override bind to 0.0.0.0:9090 (gunicorn.conf.py defaults to 127.0.0.1
# for use behind nginx in Docker/K8s).
cd "$SCRIPT_DIR/src"
gunicorn -c "$SCRIPT_DIR/deploy/docker/gunicorn.conf.py" \
  --bind 0.0.0.0:9090 \
  --workers "$WORKERS" \
  --threads "${GUNICORN_THREADS:-4}" \
  app:app
