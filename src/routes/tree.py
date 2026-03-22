from pathlib import Path

from flask import Blueprint, jsonify

import jobs
from services.jar_parser import build_tree

bp = Blueprint("tree", __name__)


@bp.route("/api/tree/<job_id>")
def tree(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        return jsonify(error="Job not found"), 404

    jar_path = Path(job.get("jar_path", ""))
    if not jar_path.exists():
        return jsonify(error="JAR file not found"), 404

    try:
        data = build_tree(jar_path)
        data["jar_name"] = jar_path.name
        return jsonify(data)
    except Exception as exc:
        return jsonify(error=str(exc)), 500
