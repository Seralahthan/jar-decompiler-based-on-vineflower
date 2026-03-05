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
(sleep 1.5 && open "http://127.0.0.1:9090") &

# ── Start Flask ──────────────────────────────────────────
echo ""
echo "  ┌──────────────────────────────────────────┐"
echo "  │   JAR Decompiler is running              │"
echo "  │   Open: http://127.0.0.1:9090            │"
echo "  │   Press Ctrl+C to stop                   │"
echo "  └──────────────────────────────────────────┘"
echo ""

python app.py
