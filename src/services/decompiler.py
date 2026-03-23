import os
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path

import jobs
from config import OUTPUT_DIR, UPLOAD_DIR, VINEFLOWER_JAR


def decompile_job(job_id: str, jar_path: Path):
    """Run Vineflower decompiler in a background thread for full JAR decompilation."""
    def update(status, message, progress):
        jobs.update_job(job_id, status=status, message=message, progress=progress)

    out_dir = OUTPUT_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    result_zip = OUTPUT_DIR / f"{job_id}.zip"

    try:
        update("running", "Starting decompiler\u2026", 10)

        java_bin = shutil.which("java")
        if not java_bin:
            raise RuntimeError("Java not found. Please install Java 11+ and ensure it is on your PATH.")

        threads = max(1, (os.cpu_count() or 2) - 1)
        cmd = [
            java_bin,
            "-Xmx2g",
            "-XX:+UseG1GC",
            "-XX:G1HeapRegionSize=16m",
            "-XX:+ParallelRefProcEnabled",
            "-jar", str(VINEFLOWER_JAR),
            f"-dht={threads}",
            str(jar_path),
            str(out_dir),
        ]

        update("running", "Decompiling \u2014 this may take a moment\u2026", 30)

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

        if proc.returncode != 0:
            stderr = proc.stderr.strip() or proc.stdout.strip()
            raise RuntimeError(f"Decompiler exited with code {proc.returncode}:\n{stderr}")

        update("running", "Packaging results into ZIP\u2026", 80)

        decompiled_items = list(out_dir.iterdir())
        if not decompiled_items:
            raise RuntimeError("Decompiler produced no output. The JAR may be empty or unreadable.")

        if len(decompiled_items) == 1 and decompiled_items[0].suffix == ".jar":
            sources_jar = decompiled_items[0]
            extract_dir = out_dir / "sources"
            extract_dir.mkdir()
            with zipfile.ZipFile(sources_jar, "r") as zf:
                zf.extractall(extract_dir)
            sources_jar.unlink()

        jar_stem = jar_path.stem
        with zipfile.ZipFile(result_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in out_dir.rglob("*"):
                if file_path.is_file():
                    arcname = Path(jar_stem) / file_path.relative_to(out_dir)
                    zf.write(file_path, arcname)

        java_count = sum(1 for f in out_dir.rglob("*.java"))
        total_count = sum(1 for f in out_dir.rglob("*") if f.is_file())

        # Populate the class cache from the full decompile output so that
        # future per-class requests (same or different job) get instant results.
        jar_hash = jobs.get_job(job_id).get("jar_hash", "") if jobs.get_job(job_id) else ""
        if jar_hash:
            src_root = out_dir / "sources" if (out_dir / "sources").is_dir() else out_dir
            for java_file in src_root.rglob("*.java"):
                try:
                    rel = java_file.relative_to(src_root).as_posix()
                    class_path = rel.replace(".java", ".class")
                    if jobs.get_class_cache(jar_hash, class_path) is None:
                        source = java_file.read_text(encoding="utf-8", errors="replace")
                        jobs.set_class_cache(jar_hash, class_path, source)
                except Exception:
                    continue

        update("done", f"Done! {java_count} Java source files decompiled ({total_count} total files).", 100)
        jobs.update_job(job_id, result_path=str(result_zip), filename=f"{jar_stem}-decompiled.zip")

    except subprocess.TimeoutExpired:
        update("error", "Decompilation timed out after 30 minutes.", 0)
    except Exception as exc:
        update("error", str(exc), 0)
    finally:
        # Keep the uploaded JAR for on-demand per-class decompilation.
        shutil.rmtree(out_dir, ignore_errors=True)


def decompile_single_class(job_id: str, class_path: str, jar_path: Path) -> str:
    """
    Decompile a single .class file from the JAR using Vineflower.
    Returns the decompiled Java source as a string.
    Raises RuntimeError or subprocess.TimeoutExpired on failure.
    """
    req_id = uuid.uuid4().hex
    staging_dir = UPLOAD_DIR / job_id / "cls_stage" / req_id
    cls_out_dir = UPLOAD_DIR / job_id / "cls_out" / req_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    cls_out_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(jar_path, "r") as zf:
            zf.extract(class_path, staging_dir)

        extracted = staging_dir / class_path

        java_bin = shutil.which("java")
        if not java_bin:
            raise RuntimeError("Java not found on PATH")

        cmd = [
            java_bin, "-Xmx256m",
            "-jar", str(VINEFLOWER_JAR),
            str(extracted),
            str(cls_out_dir),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        java_files = list(cls_out_dir.rglob("*.java"))
        if not java_files:
            err = proc.stderr.strip() or proc.stdout.strip() or "No output produced"
            raise RuntimeError(f"Decompiler produced no output: {err}")

        return java_files[0].read_text(encoding="utf-8", errors="replace")

    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)
        shutil.rmtree(cls_out_dir, ignore_errors=True)
