# ── Stage: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim

# Install Java 21 (JRE only — enough to run vineflower.jar)
RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-21-jre-headless && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer-cache friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app.py .
COPY templates/ templates/
COPY static/ static/
COPY lib/ lib/

# Pre-create runtime directories
RUN mkdir -p uploads output

EXPOSE 5000

CMD ["python", "app.py"]
