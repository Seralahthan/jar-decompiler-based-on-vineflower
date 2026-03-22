# ── Stage: runtime ──────────────────────────────────────────────────────────
FROM python:3.13-slim

# Install Java 21 (JRE only) and Redis server
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        openjdk-21-jre-headless \
        redis-server \
        nginx \
        openssl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer-cache friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/app.py src/config.py src/jobs.py src/pools.py ./
COPY deploy/docker/gunicorn.conf.py deploy/docker/entrypoint.sh ./
COPY deploy/docker/nginx.conf /etc/nginx/nginx.conf
COPY src/routes/ routes/
COPY src/services/ services/
COPY src/templates/ templates/
COPY src/static/ static/
COPY src/lib/ lib/

# Pre-create runtime directories and nginx temp dirs (owned by appuser)
RUN mkdir -p uploads output \
    && mkdir -p /tmp/certs /tmp/nginx-client-body /tmp/nginx-proxy \
                /tmp/nginx-fastcgi /tmp/nginx-uwsgi /tmp/nginx-scgi

# Run as non-root user for security
RUN useradd -m appuser \
    && chown -R appuser:appuser /app /tmp/certs \
       /tmp/nginx-client-body /tmp/nginx-proxy \
       /tmp/nginx-fastcgi /tmp/nginx-uwsgi /tmp/nginx-scgi

USER appuser

ENV HOST_PORT=9090
ENV REDIS_URL=redis://localhost:6379/0
# 8443 = HTTPS, 8080 = HTTP (redirects to HTTPS)
EXPOSE 8443 8080

# Entrypoint starts bundled Redis, then launches Gunicorn
CMD ["./entrypoint.sh"]
