# Toolsku PDF Compression

A small FastAPI app that accepts one PDF, runs it through Ghostscript and qpdf in a background queue, and returns a compressed PDF.

## Run locally

Install Python dependencies with `uv sync`. Install Ghostscript (`gs`) and qpdf on the machine running the app, then start it with:

```sh
uv run python -m toolsku
```

Open `http://127.0.0.1:8000` in a browser. The app accepts PDFs up to 50 MB. It keeps uploads and results in a temporary directory and clears them when the app stops.

The queue and job status are held in memory for this single-process app. Use one application worker; a multi-process or persistent queue is needed before running multiple workers or distributing jobs across servers.

## Run with Docker Compose

Install Docker Engine with the Compose plugin, then build and start the app:

```sh
docker compose up --build -d
```

Open `http://localhost:8000`. Follow the app logs with `docker compose logs -f pdf-compressor` and stop the app with `docker compose down`. The Compose setup keeps application logs in a named volume. Uploaded and compressed PDFs are temporary and are cleared when the container stops.

The app uses an in-memory queue and job store, so keep one Compose service instance and one Uvicorn worker. Use a TLS reverse proxy when exposing the service publicly.
