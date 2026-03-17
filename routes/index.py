from pathlib import Path

from flask import Blueprint, jsonify, request

import jobs
from pools import QueueFullError, submit_full_decompile
from services.indexer import index_job

bp = Blueprint("index", __name__)


@bp.route("/api/build-index/<job_id>", methods=["POST"])
def build_index(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        return jsonify(error="Job not found"), 404
    status = job.get("index_status", "idle")
    if status == "done":
        return jsonify(ok=True), 200
    if status == "running":
        return jsonify(ok=False, status="running"), 202

    jobs.update_job(job_id, index_status="queued", index_progress=0)

    jar_path = Path(job.get("jar_path", ""))
    try:
        submit_full_decompile(index_job, job_id, jar_path)
    except QueueFullError as exc:
        return jsonify(error=str(exc)), 503

    return jsonify(ok=True), 202


@bp.route("/api/index-status/<job_id>")
def index_status(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        return jsonify(error="Job not found"), 404
    return jsonify(
        status=job.get("index_status", "idle"),
        progress=int(job.get("index_progress", 0)),
    )


@bp.route("/api/search-methods/<job_id>")
def search_methods(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        return jsonify(error="Job not found"), 404
    if job.get("index_status") != "done":
        return jsonify(error="Index not ready"), 400

    query = request.args.get("q", "").strip().lower()
    if len(query) < 2:
        return jsonify(results=[])

    method_index = jobs.get_method_index(job_id)
    results = []
    for method_name, locations in method_index.items():
        if query in method_name.lower():
            for loc in locations[:5]:
                file_path, _, line_str = loc.rpartition(":")
                class_path = file_path.replace(".java", ".class")
                results.append({
                    "method": method_name,
                    "class_path": class_path,
                    "line": int(line_str) if line_str.isdigit() else 1,
                })
        if len(results) >= 100:
            break
    return jsonify(results=results[:100])
