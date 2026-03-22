import os

from flask import Flask

from config import MAX_UPLOAD_MB
from routes import main, upload, index, tree, decompile

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

app.register_blueprint(main.bp)
app.register_blueprint(upload.bp)
app.register_blueprint(index.bp)
app.register_blueprint(tree.bp)
app.register_blueprint(decompile.bp)

# Local development: run with Flask dev server + cleanup thread.
# Production: use  gunicorn -c gunicorn.conf.py app:app  (cleanup
# thread is started via the post_fork hook in gunicorn.conf.py).
if __name__ == "__main__":
    import threading
    from services.cleanup import cleanup_old_jobs

    threading.Thread(target=cleanup_old_jobs, daemon=True).start()
    port = int(os.environ.get("HOST_PORT", 9090))
    app.run(debug=False, host="0.0.0.0", port=port)
