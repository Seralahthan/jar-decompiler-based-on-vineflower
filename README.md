# JAR Decompiler

A local web application that decompiles Java `.jar` files into human-readable Java source code using the [Vineflower](https://github.com/Vineflower/vineflower) decompiler (a community fork of JetBrains FernFlower).

## Features

- Drag-and-drop or browse-to-select JAR upload
- Split-pane workspace with a file tree and source viewer
- Lazy per-class decompilation — click any class to decompile and view it instantly
- Per-session class cache so each class is only decompiled once
- Full background decompilation with ZIP download of all sources
- Syntax-highlighted Java source via highlight.js
- Resizable tree/source panels
- Automatic cleanup of temporary files after 1 hour
- Runs entirely locally — your JARs never leave your machine

## Running with Docker

No host dependencies needed — Java and Python are bundled inside the image.

### Using the pre-built image (recommended)

```bash
docker run -p 9090:9090 ghcr.io/seralahthan/jar-decompiler-based-on-vineflower:latest
```

The app will be available at `http://localhost:9090`.

### Building locally

```bash
docker compose up --build
```

The app will be available at `http://localhost:9090` by default.

### Configuration

Copy `.env.example` to `.env` and adjust for your environment:

```bash
cp .env.example .env
```

| Variable | Default | Description |
| --- | --- | --- |
| `PLATFORM` | `linux/arm64` | CPU architecture (`linux/amd64` or `linux/arm64`) |
| `HOST_PORT` | `9090` | Host port to access the app |
| `MEM_LIMIT` | `2g` | Container memory limit |
| `CPUS` | `4` | CPU cores available to the container |

Uploads and output are persisted in named Docker volumes across container restarts.

## Running locally (without Docker)

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
2. Install Flask automatically
3. Start the app at `http://127.0.0.1:5000` — on macOS the browser opens automatically

Press **Ctrl+C** to stop.

## Project structure

```text
jar-decompiler-based-on-vineflower/
├── app.py              # Flask backend
├── requirements.txt    # Python deps (Flask)
├── run.sh              # One-command launcher
├── Dockerfile
├── docker-compose.yml
├── .env.example        # Docker config template
├── .github/
│   └── workflows/
│       └── docker-publish.yml  # Publishes image to ghcr.io on version tags
├── lib/
│   └── vineflower.jar  # Vineflower decompiler
├── templates/
│   └── index.html      # Frontend HTML
├── static/
│   ├── css/style.css
│   └── js/app.js
├── uploads/            # Temp upload storage (auto-cleaned)
└── output/             # Temp output storage (auto-cleaned)
```

## How it works

1. Upload a `.jar` through the web UI
2. The file tree is built immediately by reading the JAR's entries — no waiting for decompilation
3. Click any class in the tree to decompile just that class on demand; results are cached for the session
4. In the background, Vineflower decompiles the full JAR and packages all sources into a ZIP
5. A banner appears when the ZIP is ready — click **Download ZIP** to get all sources at once
6. Temporary files are cleaned up automatically after 1 hour
