# Toolsku File Compression

A small FastAPI app with separate PDF and image compression flows. PDF files are processed with Ghostscript and qpdf. WebP images use the WebP tools, while JPEG and PNG export uses ImageMagick.

## Run locally

Install Python dependencies with `uv sync`. Install Ghostscript (`gs`), qpdf, the WebP tools (`cwebp`), and ImageMagick (`magick` or `convert`) on the machine running the app, then start it with:

```sh
uv run python -m toolsku
```

Open `http://127.0.0.1:8000` to choose a tool. PDF compression is at `/pdf`; image compression is at `/images`. Each flow accepts files up to 50 MB. Image compression supports static JPG, PNG, and WebP files up to 40 megapixels. Its output format defaults to the uploaded image and can be changed to JPEG, PNG, or WebP. Uploads and results stay in a temporary directory and are cleared when the app stops.

The queue and job status are held in memory for this single-process app. Use one application worker; a multi-process or persistent queue is needed before running multiple workers or distributing jobs across servers.

## Run with Docker Compose

Install Docker Engine with the Compose plugin, then build and start the app:

```sh
docker compose up --build -d
```

Open `http://localhost:8000`. Follow the app logs with `docker compose logs -f pdf-compressor` and stop the app with `docker compose down`. The Compose setup keeps application logs in a named volume. Uploaded and compressed files are temporary and are cleared when the container stops.

The app uses an in-memory queue and job store, so keep one Compose service instance and one Uvicorn worker. Use a TLS reverse proxy when exposing the service publicly.
