# JAR Decompiler

A local web application that decompiles Java `.jar` files into human-readable Java source code using the [Vineflower](https://github.com/Vineflower/vineflower) decompiler (a community fork of JetBrains FernFlower).

## Features

- Drag-and-drop or browse-to-select JAR upload
- Live progress bar during decompilation
- Download decompiled Java sources as a single ZIP archive
- Automatic cleanup of temporary files after 1 hour
- Runs entirely locally — your JARs never leave your machine

## Requirements

| Requirement | Version |
|---|---|
| macOS | 10.15+ |
| Java (JDK/JRE) | 11 or later |
| Python | 3.9 or later |

Install Java via Homebrew if needed:
```bash
brew install openjdk
```

## Running the app

```bash
chmod +x run.sh   # one-time
./run.sh
```

The script will:
1. Create a Python virtual environment (`.venv/`) on first run
2. Install Flask automatically
3. Open your browser to `http://127.0.0.1:5000`

Press **Ctrl+C** to stop.

## Project structure

```
jar-decompiler-based-on-fern-flower/
├── app.py              # Flask backend
├── requirements.txt    # Python deps (Flask)
├── run.sh              # One-command launcher
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

1. You upload a `.jar` through the web UI
2. Flask saves the JAR temporarily and spawns a background thread
3. The thread runs `java -jar vineflower.jar <input.jar> <output_dir>`
4. The decompiled `.java` files are packaged into a ZIP
5. You click **Download ZIP** to get the results
6. Temporary files are cleaned up automatically after 1 hour
