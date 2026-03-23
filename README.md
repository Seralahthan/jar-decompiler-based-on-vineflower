# JAR Decompiler

A web application that decompiles Java `.jar` files into human-readable Java source code using the [Vineflower](https://github.com/Vineflower/vineflower) decompiler (a community fork of JetBrains FernFlower).

## Features

- Drag-and-drop or browse-to-select JAR upload
- Split-pane workspace with a file tree and source viewer
- Lazy per-class decompilation — click any class to decompile and view it instantly
- Content-based class cache (SHA-256) — same JAR content shares cached results across sessions
- Full background decompilation with ZIP download of all sources
- Method indexing and search across decompiled sources
- Syntax-highlighted Java source via highlight.js
- Resizable tree/source panels
- Auto-redirect to upload page when session expires
- Automatic cleanup of temporary files after 4 hours
- Redis-backed shared state (with in-memory fallback for local development)
- HTTPS with TLS termination via nginx (Docker/K8s deployments)
- Horizontal Pod Autoscaler support for Kubernetes

---

## Quick Start

### Running locally (without Docker)

**Requirements:** Java 11+ and Python 3.9+ must be on your `PATH`.

Install Java if needed:

- **macOS:** `brew install openjdk`
- **Ubuntu/Debian:** `sudo apt install openjdk-21-jre-headless`
- **Other:** download from [adoptium.net](https://adoptium.net)

```bash
chmod +x run.sh   # one-time
./run.sh
```

The script will:

1. Create a Python virtual environment (`.venv/`) on first run
2. Install dependencies automatically
3. Detect Redis — uses 1 Gunicorn worker without Redis (in-memory store), or 4 workers with Redis (shared state)
4. Start the app at `http://127.0.0.1:9090` — on macOS the browser opens automatically

Press **Ctrl+C** to stop.

#### Optional: Run with Redis locally

Install and start Redis for multi-worker support and persistent state:

```bash
# macOS
brew install redis && brew services start redis

# Ubuntu/Debian
sudo apt install redis-server && sudo systemctl start redis
```

Override defaults via environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `GUNICORN_WORKERS` | `1` (no Redis) / `4` (with Redis) | Number of Gunicorn worker processes |
| `GUNICORN_THREADS` | `4` | Threads per worker |

---

### Running with Docker

No host dependencies needed — Java, Python, Redis, and nginx are bundled inside the image.

#### Using the pre-built image (recommended)

```bash
docker run -d --name jar-decompiler \
  -p 443:8443 -p 80:8080 \
  ghcr.io/seralahthan/jar-decompiler-based-on-vineflower:latest
```

The app will be available at `https://localhost` (self-signed certificate — accept the browser warning).

> The `--platform` flag is not needed — Docker automatically selects the correct architecture (`amd64` or `arm64`) from the multi-arch image.

To apply resource limits:

```bash
docker run -d --name jar-decompiler \
  -p 443:8443 -p 80:8080 \
  --memory=6g --cpus=4 \
  ghcr.io/seralahthan/jar-decompiler-based-on-vineflower:latest
```

To use your own TLS certificates:

```bash
docker run -d --name jar-decompiler \
  -p 443:8443 -p 80:8080 \
  -v /path/to/certs:/certs \
  ghcr.io/seralahthan/jar-decompiler-based-on-vineflower:latest
```

Mount a directory containing `tls.crt` and `tls.key` at `/certs`. If not provided, a self-signed certificate is generated automatically.

#### Building locally with Docker Compose

```bash
cd deploy/docker
docker compose up --build
```

Copy `deploy/docker/.env.example` to `deploy/docker/.env` and adjust for your environment:

| Variable | Default | Description |
| --- | --- | --- |
| `PLATFORM` | `linux/arm64` | CPU architecture (`linux/amd64` or `linux/arm64`) |
| `HOST_PORT` | `9090` | Gunicorn internal port |
| `MEM_LIMIT` | `6g` | Container memory limit |
| `CPUS` | `4` | CPU cores available to the container |
| `GUNICORN_WORKERS` | `4` | Gunicorn worker processes |
| `GUNICORN_THREADS` | `4` | Threads per worker |
| `FULL_DECOMPILE_POOL_TOTAL` | `2` | Concurrent full-JAR decompile slots (each uses -Xmx2g) |
| `CLASS_DECOMPILE_POOL_TOTAL` | `8` | Concurrent per-class decompile slots (each uses -Xmx256m) |

---

### Running on Kubernetes

#### Prerequisites

- A Kubernetes cluster (e.g., minikube, EKS, GKE)
- `kubectl` configured to access the cluster

#### Deploy

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/redis-deployment.yaml -f deploy/k8s/redis-service.yaml
kubectl apply -f deploy/k8s/app-deployment.yaml -f deploy/k8s/app-service.yaml
kubectl apply -f deploy/k8s/hpa.yaml       # optional: enables auto-scaling
kubectl apply -f deploy/k8s/ingress.yaml    # optional: external access via Ingress
```

#### Access via port-forward

```bash
kubectl -n jar-decompiler port-forward svc/jar-decompiler-svc 8443:443
```

Then open `https://localhost:8443` (accept the self-signed certificate warning).

#### HPA auto-scaling

The HPA scales pods between 1–5 replicas based on CPU utilization (target: 60%). Scale-down stabilization is set to 60 seconds for faster response during testing.

#### Clean up

```bash
kubectl delete namespace jar-decompiler
```

---

## Project Structure

```text
jar-decompiler-based-on-vineflower/
├── README.md                           # This file
├── requirements.txt                    # Python dependencies
├── run.sh                              # Local development launcher
│
├── src/                                # Application source code
│   ├── app.py                          # Flask entry point & blueprint registration
│   ├── config.py                       # Configuration (paths, pools, Redis, TTLs)
│   ├── jobs.py                         # Job store (Redis with in-memory fallback)
│   ├── pools.py                        # Thread pool executors with backpressure
│   ├── lib/
│   │   └── vineflower.jar              # Vineflower decompiler binary
│   ├── routes/
│   │   ├── main.py                     # GET / — renders UI
│   │   ├── upload.py                   # POST /api/upload, start-decompile, status, download
│   │   ├── decompile.py                # POST /api/decompile-class — per-class decompilation
│   │   ├── tree.py                     # GET /api/tree — JAR file tree
│   │   └── index.py                    # POST /api/build-index, search-methods
│   ├── services/
│   │   ├── decompiler.py               # Full-JAR and per-class decompilation logic
│   │   ├── jar_parser.py               # JAR entry parsing into tree structure
│   │   ├── indexer.py                  # Method indexing and search
│   │   └── cleanup.py                  # Daemon thread for expired job cleanup
│   ├── templates/
│   │   └── index.html                  # Single-page application UI
│   └── static/
│       ├── css/style.css               # Styling
│       └── js/app.js                   # Frontend JavaScript
│
├── deploy/                             # Deployment configurations
│   ├── docker/
│   │   ├── Dockerfile                  # Multi-arch runtime image
│   │   ├── docker-compose.yml          # Local Docker orchestration
│   │   ├── entrypoint.sh               # Container startup (Redis + nginx + Gunicorn)
│   │   ├── nginx.conf                  # TLS termination & reverse proxy
│   │   ├── gunicorn.conf.py            # Production WSGI configuration
│   │   └── .env.example                # Environment variable template
│   └── k8s/
│       ├── namespace.yaml
│       ├── app-deployment.yaml         # App pod (HTTPS on 8443, HTTP redirect on 8080)
│       ├── app-service.yaml            # ClusterIP service
│       ├── redis-deployment.yaml       # Redis pod
│       ├── redis-service.yaml          # Redis ClusterIP service
│       ├── hpa.yaml                    # Horizontal Pod Autoscaler
│       └── ingress.yaml                # Ingress for external access
│
├── tests/                              # Integration test suites
│   ├── requirements.txt                # Test dependencies
│   ├── fixtures/                       # Test data
│   │   ├── build_jars.sh               # Compiles Java sources into fixture JARs
│   │   ├── java8/, java11/, java17/, java21/  # Java source fixtures
│   │   └── jars/                       # Generated JARs (gitignored)
│   ├── docker/                         # Docker/local integration tests
│   │   ├── conftest.py                 # Shared fixtures and helpers
│   │   ├── test_workflow.py            # Upload → decompile → download flow
│   │   ├── test_accuracy.py            # Decompilation output validation
│   │   ├── test_cache.py               # Cache deduplication and performance
│   │   └── test_concurrency.py         # Parallel uploads and decompilation
│   └── k8s/                            # Kubernetes scenario tests
│       ├── README.md                   # K8s test setup and run instructions
│       ├── conftest.py                 # Shared K8s fixtures
│       ├── test_scenario01_single_pod.py   # Single pod functional tests
│       ├── test_scenario02_hpa_scaling.py  # HPA scale-up/down verification
│       └── test_scenario03_full_suite.py   # Full suite (dedup, concurrency, accuracy)
│
└── .github/
    └── workflows/
        └── docker-publish.yml          # CI: builds & pushes image on version tags
```

---

## How It Works

1. **Upload** a `.jar` through the web UI (drag-and-drop or file picker)
2. The **file tree** is built immediately by reading JAR entries — no decompilation needed
3. **Click any class** to decompile just that class on demand; results are cached by JAR content hash (SHA-256)
4. **Build Index** to scan all methods — enables method search across the entire JAR
5. **Start Full Decompile** to decompile the entire JAR in the background; download all sources as a ZIP when done
6. Temporary files are cleaned up automatically after 4 hours

### Architecture highlights

- **Content-based deduplication**: uploading the same JAR multiple times (even across sessions) reuses cached decompilation results
- **Distributed locking**: Redis-backed locks prevent redundant decompilation across Gunicorn workers and K8s pods
- **Bounded thread pools**: separate pools for full-JAR (-Xmx2g) and per-class (-Xmx256m) decompilation prevent memory starvation; queue saturation returns 503 immediately
- **TLS termination**: nginx handles HTTPS (port 8443) and HTTP→HTTPS redirect (port 8080), proxying to Gunicorn internally

---

## Running Tests

### Test prerequisites

```bash
# Build fixture JARs (one-time, requires Java 8/11/17/21)
cd tests/fixtures && ./build_jars.sh && cd ../..

# Install test dependencies
pip install -r tests/requirements.txt
```

### Docker / Local integration tests

These tests hit the app via HTTP API. The app must be running first.

**Against local app** (started via `./run.sh`):

```bash
DECOMPILER_URL=http://localhost:9090 pytest tests/docker/ -v
```

**Against Docker container**:

```bash
docker run -d --name jar-decompiler -p 443:8443 -p 80:8080 \
  ghcr.io/seralahthan/jar-decompiler-based-on-vineflower:latest

DECOMPILER_URL=https://localhost pytest tests/docker/ -v
```

| Variable | Default | Description |
| --- | --- | --- |
| `DECOMPILER_URL` | `https://localhost` | App endpoint URL |
| `DECOMPILER_CONTAINER` | `jar-decompiler-test` | Docker container name (for Redis flush fallback) |

### Kubernetes tests

Requires a running K8s deployment with port-forward active. See [tests/k8s/README.md](tests/k8s/README.md) for detailed setup.

```bash
# Scenario 01: Single pod functional tests
pytest tests/k8s/test_scenario01_single_pod.py -v

# Scenario 02: HPA auto-scaling (needs metrics-server)
pytest tests/k8s/test_scenario02_hpa_scaling.py -v -s

# Scenario 03: Full suite (dedup, concurrency, multi-version)
pytest tests/k8s/test_scenario03_full_suite.py -v

# All scenarios
pytest tests/k8s/ -v -s
```

| Variable | Default | Description |
| --- | --- | --- |
| `K8S_BASE_URL` | `https://localhost:8443` | App endpoint via port-forward |
| `K8S_NAMESPACE` | `jar-decompiler` | Kubernetes namespace |

---

## CI/CD

The GitHub Actions workflow (`.github/workflows/docker-publish.yml`) automatically builds and pushes a multi-arch Docker image (`linux/amd64` + `linux/arm64`) to `ghcr.io` when a version tag is pushed:

```bash
git tag v1.2.0
git push origin v1.2.0
```

The image is tagged with the version number, major.minor, and `latest`.
