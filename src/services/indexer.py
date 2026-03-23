import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import jobs
from config import OUTPUT_DIR, VINEFLOWER_JAR

_JAVA_METHOD_RE = re.compile(
    r'^(?!return\b|throw\b|new\b|if\b|else\b|for\b|while\b|do\b|switch\b|catch\b|try\b|assert\b|case\b|break\b|continue\b)'
    r'(?:(?:public|private|protected)\s+)?'
    r'(?:(?:static|final|abstract|synchronized|native|default|strictfp)\s+)*'
    r'[\w<>\[\]?,\s]+?\s+'   # return type (mandatory)
    r'(\w+)\s*\('             # method name
)
_SKIP_NAMES = frozenset({
    'if', 'for', 'while', 'switch', 'catch', 'try', 'new', 'return',
    'class', 'interface', 'enum', 'assert', 'throw', 'synchronized',
    'this', 'super', 'import', 'package', 'else',
})


def build_method_index(src_root: Path) -> dict:
    """Scan decompiled .java files and return method_name -> [file:line, ...] index."""
    index: dict[str, list[str]] = {}
    for java_file in src_root.rglob("*.java"):
        try:
            lines = java_file.read_text(encoding="utf-8", errors="replace").splitlines()
            rel = java_file.relative_to(src_root).as_posix()
            for lineno, line in enumerate(lines, 1):
                m = _JAVA_METHOD_RE.match(line.lstrip())
                if m:
                    name = m.group(1)
                    if name and name not in _SKIP_NAMES:
                        index.setdefault(name, []).append(f"{rel}:{lineno}")
        except Exception:
            continue
    return index


def index_job(job_id: str, jar_path: Path):
    """Run Vineflower for method indexing — keeps decompiled output, no ZIP."""
    def update_idx(status, progress):
        jobs.update_job(job_id, index_status=status, index_progress=progress)

    index_dir = OUTPUT_DIR / f"{job_id}_index"
    index_dir.mkdir(parents=True, exist_ok=True)

    try:
        update_idx("running", 10)
        java_bin = shutil.which("java")
        if not java_bin:
            raise RuntimeError("Java not found on PATH.")

        threads = max(1, (os.cpu_count() or 2) - 2)
        cmd = [
            java_bin, "-Xmx2g", "-XX:+UseG1GC",
            "-XX:G1HeapRegionSize=16m", "-XX:+ParallelRefProcEnabled",
            "-jar", str(VINEFLOWER_JAR),
            f"-dht={threads}", "-mpm=10000",
            str(jar_path), str(index_dir),
        ]

        update_idx("running", 20)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if proc.returncode != 0:
            raise RuntimeError(f"Decompiler exited with code {proc.returncode}")

        update_idx("running", 75)

        # Vineflower may output a sources JAR instead of plain files
        items = list(index_dir.iterdir())
        if len(items) == 1 and items[0].suffix == ".jar":
            src_root = index_dir / "sources"
            src_root.mkdir()
            with zipfile.ZipFile(items[0], "r") as zf:
                zf.extractall(src_root)
            items[0].unlink()
        else:
            src_root = index_dir

        update_idx("running", 85)
        method_index = build_method_index(src_root)

        job = jobs.get_job(job_id)
        jar_hash = job.get("jar_hash", "") if job else ""
        jobs.set_method_index(jar_hash, method_index)

        # Populate the class cache so that any job with the same JAR hash
        # gets instant results without per-class Vineflower invocations.
        if jar_hash:
            update_idx("running", 90)
            for java_file in src_root.rglob("*.java"):
                try:
                    rel = java_file.relative_to(src_root).as_posix()
                    class_path = rel.replace(".java", ".class")
                    if jobs.get_class_cache(jar_hash, class_path) is None:
                        source = java_file.read_text(encoding="utf-8", errors="replace")
                        jobs.set_class_cache(jar_hash, class_path, source)
                except Exception:
                    continue

        jobs.update_job(job_id, index_status="done", index_progress=100)

    except subprocess.TimeoutExpired:
        update_idx("error", 0)
    except Exception as exc:
        jobs.update_job(job_id, index_status="error", index_error=str(exc), index_progress=0)
