#!/bin/sh
# Start the bundled Redis server in the background (lightweight, ~5MB RSS),
# then hand off to Gunicorn as the main process.
#
# In Kubernetes / docker-compose you can override REDIS_URL to point to an
# external Redis instance; the bundled one will still start but remain idle.

redis-server \
  --daemonize yes \
  --port 6379 \
  --bind 127.0.0.1 \
  --dir /tmp \
  --maxmemory 256mb \
  --maxmemory-policy allkeys-lru \
  --loglevel warning \
  --protected-mode no

exec gunicorn -c gunicorn.conf.py app:app
