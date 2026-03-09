import threading
from pathlib import Path

from flask import Blueprint, jsonify, request

from jobs import jobs, jobs_lock
from services.indexer import index_job

bp = Blueprint("index", __name__)


@bp.route("/api/build-index/<job_id>", methods=["POST"])
def build_index(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        return jsonify(error="Job not found"), 404
    status = job.get("index_status", "idle")
    if status == "done":
        return jsonify(ok=True), 200
    if status == "running":
        return jsonify(ok=False, status="running"), 202
    with jobs_lock:
        jobs[job_id]["index_status"]   = "queued"
        jobs[job_id]["index_progress"] = 0
    jar_path = Path(job.get("jar_path", ""))
    threading.Thread(target=index_job, args=(job_id, jar_path), daemon=True).start()
    return jsonify(ok=True), 202


@bp.route("/api/index-status/<job_id>")
def index_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        return jsonify(error="Job not found"), 404
    return jsonify(
        status=job.get("index_status", "idle"),
        progress=job.get("index_progress", 0),
    )


@bp.route("/api/search-methods/<job_id>")
def search_methods(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        return jsonify(error="Job not found"), 404
    if job.get("index_status") != "done":
        return jsonify(error="Index not ready"), 400
    query = request.args.get("q", "").strip().lower()
    if len(query) < 2:
        return jsonify(results=[])
    method_index: dict = job.get("method_index", {})
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
