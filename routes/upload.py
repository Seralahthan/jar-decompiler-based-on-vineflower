import time
import uuid
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_file

import jobs
from config import UPLOAD_DIR
from pools import QueueFullError, submit_full_decompile
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

    jobs.create_job(job_id, str(jar_path), time.time())

    return jsonify(job_id=job_id), 202


@bp.route("/api/start-decompile/<job_id>", methods=["POST"])
def start_decompile(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        return jsonify(error="Job not found"), 404
    if job.get("status") != "queued":
        return jsonify(error="Decompilation already started"), 400

    jar_path = Path(job.get("jar_path", ""))
    try:
        submit_full_decompile(decompile_job, job_id, jar_path)
    except QueueFullError as exc:
        return jsonify(error=str(exc)), 503

    return jsonify(ok=True), 202


@bp.route("/api/status/<job_id>")
def status(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        return jsonify(error="Job not found"), 404
    return jsonify(
        status=job["status"],
        message=job["message"],
        progress=int(job.get("progress", 0)),
    )


@bp.route("/api/download/<job_id>")
def download(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        abort(404)
    if job.get("status") != "done":
        abort(400)
    result_path = job.get("result_path")
    filename = job.get("filename", f"{job_id}.zip")
    if not result_path or not Path(result_path).exists():
        abort(404)
    return send_file(result_path, as_attachment=True, download_name=filename)
