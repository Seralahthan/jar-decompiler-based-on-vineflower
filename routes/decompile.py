import subprocess
import zipfile
from pathlib import Path

from flask import Blueprint, jsonify, request

from config import OUTPUT_DIR
from jobs import jobs, jobs_lock
from services.decompiler import decompile_single_class

bp = Blueprint("decompile", __name__)


@bp.route("/api/decompile-class/<job_id>", methods=["POST"])
def decompile_class(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        return jsonify(error="Job not found"), 404

    body = request.get_json(silent=True) or {}
    class_path = body.get("class_path", "")

    if not class_path.endswith(".class"):
        return jsonify(error="Invalid class path: must end with .class"), 400
    segments = class_path.split("/")
    if any(s in ("", "..") for s in segments[:-1]):
        return jsonify(error="Invalid class path"), 400

    # Fast cache check (CPython dict reads are thread-safe)
    cached = job["class_cache"].get(class_path)
    if cached is not None:
        return jsonify(source=cached, cached=True)

    # If the method index was built, the class is already decompiled on disk
    java_rel = class_path.replace(".class", ".java")
    index_dir = OUTPUT_DIR / f"{job_id}_index"
    for candidate_root in (index_dir / "sources", index_dir):
        java_file = candidate_root / java_rel
        if java_file.exists():
            try:
                source = java_file.read_text(encoding="utf-8", errors="replace")
                job["class_cache"][class_path] = source
                return jsonify(source=source, cached=False)
            except Exception:
                pass  # fall through to per-class decompilation

    jar_path = Path(job.get("jar_path", ""))
    if not jar_path.exists():
        return jsonify(error="Source JAR no longer available"), 404

    try:
        with zipfile.ZipFile(jar_path, "r") as zf:
            jar_entries = set(zf.namelist())
    except Exception as exc:
        return jsonify(error=f"Could not read JAR: {exc}"), 500

    if class_path not in jar_entries:
        return jsonify(error="Class not found in JAR"), 404

    class_lock = job["class_lock"]

    with class_lock:
        # Double-check cache after acquiring lock
        cached = job["class_cache"].get(class_path)
        if cached is not None:
            return jsonify(source=cached, cached=True)

        try:
            source = decompile_single_class(job_id, class_path, jar_path)
            job["class_cache"][class_path] = source
            return jsonify(source=source, cached=False)
        except subprocess.TimeoutExpired:
            return jsonify(error="Per-class decompilation timed out (30s)"), 500
        except Exception as exc:
            return jsonify(error=str(exc)), 500
