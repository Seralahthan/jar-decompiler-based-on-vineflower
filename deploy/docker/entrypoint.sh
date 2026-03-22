#!/bin/sh
# Starts bundled Redis, nginx (TLS front-end), then Gunicorn (main process).

# ── TLS Certificates ──────────────────────────────────────────────────────────
# Use real certs if mounted at /certs/tls.crt + /certs/tls.key,
# otherwise generate a self-signed certificate valid for localhost.

mkdir -p /tmp/certs \
         /tmp/nginx-client-body \
         /tmp/nginx-proxy \
         /tmp/nginx-fastcgi \
         /tmp/nginx-uwsgi \
         /tmp/nginx-scgi

if [ -f /certs/tls.crt ] && [ -f /certs/tls.key ]; then
    echo "[entrypoint] Using provided TLS certificates from /certs/"
    cp /certs/tls.crt /tmp/certs/tls.crt
    cp /certs/tls.key /tmp/certs/tls.key
else
    echo "[entrypoint] No TLS certs found at /certs/ — generating self-signed certificate..."
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout /tmp/certs/tls.key \
        -out    /tmp/certs/tls.crt \
        -subj   "/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" 2>/dev/null
    echo "[entrypoint] Self-signed certificate generated."
    echo "[entrypoint] Browsers will show a security warning — accept it to proceed."
    echo "[entrypoint] To use real certs: docker run -v /path/to/certs:/certs ..."
fi

# ── Redis ─────────────────────────────────────────────────────────────────────
redis-server \
  --daemonize yes \
  --port 6379 \
  --bind 127.0.0.1 \
  --dir /tmp \
  --maxmemory 256mb \
  --maxmemory-policy allkeys-lru \
  --loglevel warning \
  --protected-mode no

# ── nginx ─────────────────────────────────────────────────────────────────────
nginx -c /etc/nginx/nginx.conf

echo ""
echo "  ┌──────────────────────────────────────────────────────┐"
echo "  │  JAR Decompiler is running                           │"
echo "  │                                                      │"
echo "  │  HTTPS → https://localhost  (port mapping: 443:8443) │"
echo "  │  HTTP  → redirects to HTTPS (port mapping:  80:8080) │"
echo "  └──────────────────────────────────────────────────────┘"
echo ""

# ── Gunicorn (PID 1) ──────────────────────────────────────────────────────────
exec gunicorn -c gunicorn.conf.py app:app
