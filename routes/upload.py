import threading
import time
import uuid
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_file

from config import UPLOAD_DIR
from jobs import jobs, jobs_lock
from services.decompiler import decompile_job

bp = Blueprint("upload", __name__)


@bp.route("/api/upload", methods=["POST"])
def upload():
    if "jar" not in request.files:
        return jsonify(error="No file part"), 400

    f = request.files["jar"]

    if not f.filename:
        return jsonify(error="No file selected"), 400

    if not f.filename.lower().endswith(".jar"):
        return jsonify(error="Only .jar files are accepted"), 400

    job_id = uuid.uuid4().hex
    job_upload_dir = UPLOAD_DIR / job_id
    job_upload_dir.mkdir(parents=True)
    jar_path = job_upload_dir / Path(f.filename).name
    f.save(str(jar_path))

    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "message": "Queued for decompilation…",
            "progress": 0,
            "created_at": time.time(),
            "jar_path": str(jar_path),
            "class_cache": {},
            "class_lock": threading.Lock(),
        }

    return jsonify(job_id=job_id), 202


@bp.route("/api/start-decompile/<job_id>", methods=["POST"])
def start_decompile(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        return jsonify(error="Job not found"), 404
    if job.get("status") != "queued":
        return jsonify(error="Decompilation already started"), 400
    jar_path = Path(job.get("jar_path", ""))
    threading.Thread(target=decompile_job, args=(job_id, jar_path), daemon=True).start()
    return jsonify(ok=True), 202


@bp.route("/api/status/<job_id>")
def status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        return jsonify(error="Job not found"), 404
    return jsonify(
        status=job["status"],
        message=job["message"],
        progress=job["progress"],
    )


@bp.route("/api/download/<job_id>")
def download(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        abort(404)
    if job.get("status") != "done":
        abort(400)
    result_path = job.get("result_path")
    filename = job.get("filename", f"{job_id}.zip")
    if not result_path or not Path(result_path).exists():
        abort(404)
    return send_file(result_path, as_attachment=True, download_name=filename)
