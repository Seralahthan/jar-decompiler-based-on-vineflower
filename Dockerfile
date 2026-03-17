# ── Stage: runtime ──────────────────────────────────────────────────────────
FROM python:3.13-slim

# Install Java 21 (JRE only — enough to run vineflower.jar)
RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-21-jre-headless && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer-cache friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app.py config.py jobs.py pools.py gunicorn.conf.py ./
COPY routes/ routes/
COPY services/ services/
COPY templates/ templates/
COPY static/ static/
COPY lib/ lib/

# Pre-create runtime directories
RUN mkdir -p uploads output

# Run as non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

ENV HOST_PORT=9090
EXPOSE 9090

# Production: Gunicorn WSGI server
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
