import os
import re
import uuid
import subprocess
import zipfile
import shutil
import threading
import time
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, abort

app = Flask(__name__)

BASE_DIR = Path(__file__).parent
LIB_DIR = BASE_DIR / "lib"
VINEFLOWER_JAR = LIB_DIR / "vineflower.jar"
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

MAX_UPLOAD_MB = 200
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

# In-memory job store: job_id -> {status, message, progress, ...}
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def cleanup_old_jobs():
    """Remove job artifacts older than 1 hour."""
    while True:
        time.sleep(300)
        now = time.time()
        with jobs_lock:
            expired = [jid for jid, job in jobs.items()
                       if now - job.get("created_at", now) > 3600]
        for jid in expired:
            _delete_job_artifacts(jid)
            with jobs_lock:
                jobs.pop(jid, None)


def _delete_job_artifacts(job_id: str):
    upload_path = UPLOAD_DIR / job_id
    output_path = OUTPUT_DIR / job_id
    result_zip = OUTPUT_DIR / f"{job_id}.zip"
    for p in (upload_path, output_path):
        shutil.rmtree(p, ignore_errors=True)
    result_zip.unlink(missing_ok=True)


def build_tree(jar_path: Path) -> dict:
    """Parse a JAR's .class entries into a nested tree structure."""
    root: dict = {}
    class_count = 0
    resource_count = 0

    with zipfile.ZipFile(jar_path, "r") as zf:
        for entry in zf.namelist():
            if entry.endswith("/"):
                continue
            parts = entry.split("/")
            filename = parts[-1]
            if not filename:
                continue
            if not filename.endswith(".class"):
                resource_count += 1
                continue

            class_count += 1
            node = root
            for part in parts[:-1]:
                if part not in node:
                    node[part] = {"type": "package", "name": part, "children": {}}
                node = node[part]["children"]

            stem = filename[:-6]  # strip .class
            is_inner = "$" in stem
            is_anon = bool(re.search(r'\$\d+$', stem))
            node[filename] = {
                "type": "class",
                "name": filename,
                "path": entry,
                "isInner": is_inner,
                "isAnonymous": is_anon,
            }

    def dict_to_list(d: dict) -> list:
        packages, classes = [], []
        for name, val in sorted(d.items()):
            if val.get("type") == "package":
                packages.append({
                    "type": "package",
                    "name": name,
                    "children": dict_to_list(val["children"]),
                })
            else:
                classes.append(val)
        return packages + classes

    return {
        "tree": dict_to_list(root),
        "class_count": class_count,
        "resource_count": resource_count,
    }


def decompile_job(job_id: str, jar_path: Path):
    """Run Vineflower decompiler in a background thread."""
    def update(status, message, progress):
        with jobs_lock:
            jobs[job_id].update(status=status, message=message, progress=progress)

    out_dir = OUTPUT_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    result_zip = OUTPUT_DIR / f"{job_id}.zip"

    try:
        update("running", "Starting decompiler…", 10)

        java_bin = shutil.which("java")
        if not java_bin:
            raise RuntimeError("Java not found. Please install Java 11+ and ensure it is on your PATH.")

        threads = max(1, (os.cpu_count() or 2) - 1)
        cmd = [
            java_bin,
            "-Xmx1g",
            "-XX:+UseG1GC",
            "-jar", str(VINEFLOWER_JAR),
            f"-dht={threads}",
            str(jar_path),
            str(out_dir),
        ]

        update("running", "Decompiling — this may take a moment…", 30)

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
        )

        if proc.returncode != 0:
            stderr = proc.stderr.strip() or proc.stdout.strip()
            raise RuntimeError(f"Decompiler exited with code {proc.returncode}:\n{stderr}")

        update("running", "Packaging results into ZIP…", 80)

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

        update("done", f"Done! {java_count} Java source files decompiled ({total_count} total files).", 100)
        with jobs_lock:
            jobs[job_id]["result_path"] = str(result_zip)
            jobs[job_id]["filename"] = f"{jar_stem}-decompiled.zip"

    except subprocess.TimeoutExpired:
        update("error", "Decompilation timed out after 15 minutes.", 0)
    except Exception as exc:
        update("error", str(exc), 0)
    finally:
        # Keep the uploaded JAR on disk for on-demand per-class decompilation.
        # The output dir (extracted sources) is no longer needed once the ZIP is built.
        shutil.rmtree(out_dir, ignore_errors=True)


# ---------- Routes ----------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
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
            # Per-class decompilation support
            "jar_path": str(jar_path),
            "class_cache": {},
            "class_lock": threading.Lock(),
        }

    t = threading.Thread(target=decompile_job, args=(job_id, jar_path), daemon=True)
    t.start()

    return jsonify(job_id=job_id), 202


@app.route("/api/status/<job_id>")
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


@app.route("/api/tree/<job_id>")
def tree(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
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


@app.route("/api/decompile-class/<job_id>", methods=["POST"])
def decompile_class(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        return jsonify(error="Job not found"), 404

    body = request.get_json(silent=True) or {}
    class_path = body.get("class_path", "")

    # Validate input
    if not class_path.endswith(".class"):
        return jsonify(error="Invalid class path: must end with .class"), 400
    segments = class_path.split("/")
    if any(s in ("", "..") for s in segments[:-1]):
        return jsonify(error="Invalid class path"), 400

    # Fast cache check (CPython dict reads are thread-safe)
    cached = job["class_cache"].get(class_path)
    if cached is not None:
        return jsonify(source=cached, cached=True)

    jar_path = Path(job.get("jar_path", ""))
    if not jar_path.exists():
        return jsonify(error="Source JAR no longer available"), 404

    # Verify the class exists in the JAR
    try:
        with zipfile.ZipFile(jar_path, "r") as zf:
            jar_entries = set(zf.namelist())
    except Exception as exc:
        return jsonify(error=f"Could not read JAR: {exc}"), 500

    if class_path not in jar_entries:
        return jsonify(error="Class not found in JAR"), 404

    class_lock: threading.Lock = job["class_lock"]

    with class_lock:
        # Double-check cache after acquiring lock
        cached = job["class_cache"].get(class_path)
        if cached is not None:
            return jsonify(source=cached, cached=True)

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
                return jsonify(error="Java not found on PATH"), 500

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
                return jsonify(error=f"Decompiler produced no output: {err}"), 500

            source = java_files[0].read_text(encoding="utf-8", errors="replace")
            job["class_cache"][class_path] = source
            return jsonify(source=source, cached=False)

        except subprocess.TimeoutExpired:
            return jsonify(error="Per-class decompilation timed out (30s)"), 500
        except Exception as exc:
            return jsonify(error=str(exc)), 500
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)
            shutil.rmtree(cls_out_dir, ignore_errors=True)


@app.route("/api/download/<job_id>")
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


if __name__ == "__main__":
    cleaner = threading.Thread(target=cleanup_old_jobs, daemon=True)
    cleaner.start()
    port = int(os.environ.get("HOST_PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
