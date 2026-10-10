from __future__ import annotations

import asyncio
import logging
import re
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from toolsku.compression import CompressionError, compress_pdf


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.propagate = False
PACKAGE_DIR = Path(__file__).parent
ASSETS_DIR = PACKAGE_DIR / "assets"
VIEWS_DIR = PACKAGE_DIR / "views"
MAX_UPLOAD_BYTES = 50_000_000
MAX_WAITING_JOBS = 8
UPLOAD_CHUNK_BYTES = 1024 * 1024
LOGS_DIR = Path.cwd() / "logs"


class DailyFileHandler(logging.Handler):
    def __init__(self, directory: Path) -> None:
        super().__init__()
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.day = date.today()
        self._remove_old_logs()
        self.file_handler = self._open_file()

    def _open_file(self) -> logging.FileHandler:
        handler = logging.FileHandler(
            self.directory / f"toolsku-{self.day.isoformat()}.log",
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        return handler

    def _remove_old_logs(self) -> None:
        cutoff = self.day - timedelta(days=7)
        prefix = "toolsku-"
        for path in self.directory.glob("toolsku-*.log"):
            try:
                log_day = date.fromisoformat(path.stem[len(prefix) :])
            except ValueError:
                continue
            if log_day < cutoff:
                path.unlink(missing_ok=True)

    def emit(self, record: logging.LogRecord) -> None:
        today = date.today()
        if today != self.day:
            self.file_handler.close()
            self.day = today
            self._remove_old_logs()
            self.file_handler = self._open_file()
        self.file_handler.emit(record)

    def close(self) -> None:
        self.file_handler.close()
        super().close()


@dataclass
class CompressionJob:
    id: str
    filename: str
    directory: Path
    source_path: Path
    output_path: Path
    original_size: int
    target_mb: int | None
    status: str = "queued"
    output_size: int | None = None
    target_met: bool | None = None
    message: str = "Waiting in the queue."

    def public_data(self) -> dict[str, object]:
        return {
            "id": self.id,
            "status": self.status,
            "filename": self.filename,
            "original_size": self.original_size,
            "output_size": self.output_size,
            "target_mb": self.target_mb,
            "target_met": self.target_met,
            "message": self.message,
            "download_url": (
                f"/api/jobs/{self.id}/download"
                if self.status == "completed" and self.output_path.is_file()
                else None
            ),
        }


async def process_queue(app: FastAPI) -> None:
    queue: asyncio.Queue[str] = app.state.queue
    jobs: dict[str, CompressionJob] = app.state.jobs

    while True:
        job_id = await queue.get()
        job = jobs.get(job_id)
        try:
            if job is None:
                logger.warning("Queued PDF job %s was not found", job_id)
                continue

            job.status = "processing"
            job.message = "Compressing your PDF. This may take a little while."
            target_bytes = job.target_mb * 1_000_000 if job.target_mb is not None else None
            logger.info(
                "PDF compression started id=%s input_bytes=%s target_mb=%s",
                job.id,
                job.original_size,
                job.target_mb,
            )
            outcome = await asyncio.to_thread(
                compress_pdf,
                job.source_path,
                job.output_path,
                target_bytes,
            )
            job.output_size = outcome.output_size
            job.target_met = outcome.target_met
            if outcome.target_met is False:
                smallest_size_mb = (outcome.output_size + 9_999) // 10_000 / 100
                job.message = (
                    f"We couldn't reduce this PDF to {job.target_mb} MB or less. "
                    f"The smallest result was {smallest_size_mb:.2f} MB. "
                    "Try a larger target."
                )
                job.status = "failed"
                logger.warning(
                    "PDF target not met id=%s output_bytes=%s target_mb=%s",
                    job.id,
                    job.output_size,
                    job.target_mb,
                )
            else:
                job.message = outcome.message
                job.status = "completed"
                logger.info(
                    "PDF compression completed id=%s output_bytes=%s target_met=%s",
                    job.id,
                    job.output_size,
                    job.target_met,
                )
        except CompressionError as exc:
            if job is not None:
                job.status = "failed"
                job.message = str(exc)
            logger.warning("PDF compression failed id=%s reason=%s", job_id, exc)
        except Exception:
            logger.exception("PDF compression failed for job %s", job_id)
            if job is not None:
                job.status = "failed"
                job.message = "Something went wrong while compressing this PDF. Try another file."
        finally:
            if job is not None:
                job.source_path.unlink(missing_ok=True)
                if job.status == "completed":
                    for path in job.directory.iterdir():
                        if path != job.output_path:
                            path.unlink(missing_ok=True)
                    logger.info("Temporary upload files cleaned id=%s", job.id)
                else:
                    shutil.rmtree(job.directory, ignore_errors=True)
                    logger.info("Temporary job files removed id=%s", job.id)
            queue.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    file_handler = DailyFileHandler(LOGS_DIR)
    logger.addHandler(file_handler)
    logger.info("Application starting")
    storage = tempfile.TemporaryDirectory(prefix="toolsku-pdf-")
    app.state.storage_root = Path(storage.name)
    app.state.jobs = {}
    app.state.queue = asyncio.Queue(maxsize=MAX_WAITING_JOBS)
    worker = asyncio.create_task(process_queue(app))
    logger.info("Compression worker started")
    try:
        yield
    finally:
        logger.info("Application shutting down")
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
        logger.info("Compression worker stopped")
        await asyncio.get_running_loop().shutdown_default_executor()
        storage.cleanup()
        logger.info("Temporary storage cleaned")
        logger.removeHandler(file_handler)
        file_handler.close()


app = FastAPI(title="Toolsku PDF Compression", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
templates = Jinja2Templates(directory=VIEWS_DIR)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    logger.info("Home page rendered")
    return templates.TemplateResponse(request=request, name="index.html", context={})


def _display_filename(filename: str | None) -> str:
    name = (filename or "document.pdf").replace("\\", "/").rsplit("/", 1)[-1]
    return name or "document.pdf"


def _parse_target(size_option: str, custom_size_mb: str | None) -> int | None:
    if size_option == "recommended":
        return None
    if size_option in {"1", "2"}:
        return int(size_option)
    if size_option != "custom":
        logger.warning("Compression request rejected reason=invalid_size_option")
        raise HTTPException(status_code=422, detail="Choose a valid compression target.")
    if custom_size_mb is None or re.fullmatch(r"[0-9]+", custom_size_mb) is None:
        logger.warning("Compression request rejected reason=invalid_custom_size")
        raise HTTPException(
            status_code=422,
            detail="Enter a whole-number target in megabytes, such as 3.",
        )
    target_mb = int(custom_size_mb)
    if target_mb < 1:
        logger.warning("Compression request rejected reason=custom_size_below_minimum")
        raise HTTPException(status_code=422, detail="The target must be at least 1 MB.")
    return target_mb


@app.post("/api/jobs", status_code=202)
async def create_job(
    file: Annotated[UploadFile, File()],
    size_option: Annotated[str, Form()] = "recommended",
    custom_size_mb: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    target_mb = _parse_target(size_option, custom_size_mb)
    filename = _display_filename(file.filename)
    if not filename.lower().endswith(".pdf"):
        logger.warning("PDF upload rejected reason=invalid_extension")
        await file.close()
        raise HTTPException(status_code=415, detail="Choose a PDF file to continue.")

    queue: asyncio.Queue[str] = app.state.queue
    if queue.full():
        logger.warning("PDF upload rejected reason=queue_full")
        await file.close()
        raise HTTPException(
            status_code=503,
            detail="The compression queue is full. Wait a moment, then try again.",
        )

    job_id = uuid.uuid4().hex
    directory = app.state.storage_root / job_id
    source_path = directory / "source.pdf"
    output_path = directory / "compressed.pdf"
    directory.mkdir()

    try:
        first_chunk = await file.read(UPLOAD_CHUNK_BYTES)
        if not first_chunk or b"%PDF-" not in first_chunk[:1024]:
            logger.warning("PDF upload rejected id=%s reason=invalid_pdf", job_id)
            raise HTTPException(status_code=415, detail="This file doesn't look like a PDF.")
        total_size = len(first_chunk)
        if total_size > MAX_UPLOAD_BYTES:
            logger.warning("PDF upload rejected id=%s reason=size_limit", job_id)
            raise HTTPException(status_code=413, detail="This PDF is larger than the 50 MB upload limit.")

        with source_path.open("wb") as destination:
            destination.write(first_chunk)
            while chunk := await file.read(UPLOAD_CHUNK_BYTES):
                total_size += len(chunk)
                if total_size > MAX_UPLOAD_BYTES:
                    logger.warning("PDF upload rejected id=%s reason=size_limit", job_id)
                    raise HTTPException(
                        status_code=413,
                        detail="This PDF is larger than the 50 MB upload limit.",
                    )
                destination.write(chunk)
    except HTTPException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    except Exception:
        logger.exception("PDF upload failed id=%s", job_id)
        shutil.rmtree(directory, ignore_errors=True)
        raise
    finally:
        await file.close()

    job = CompressionJob(
        id=job_id,
        filename=filename,
        directory=directory,
        source_path=source_path,
        output_path=output_path,
        original_size=total_size,
        target_mb=target_mb,
    )
    try:
        queue.put_nowait(job_id)
    except asyncio.QueueFull as exc:
        shutil.rmtree(directory, ignore_errors=True)
        logger.warning("PDF upload rejected id=%s reason=queue_full", job_id)
        raise HTTPException(
            status_code=503,
            detail="The compression queue is full. Wait a moment, then try again.",
        ) from exc
    app.state.jobs[job_id] = job
    logger.info(
        "PDF upload accepted id=%s input_bytes=%s target_mb=%s",
        job.id,
        job.original_size,
        job.target_mb,
    )
    return job.public_data()


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, object]:
    job = app.state.jobs.get(job_id)
    if job is None:
        logger.warning("PDF job lookup failed id=%s reason=not_found", job_id)
        raise HTTPException(status_code=404, detail="This compression job could not be found.")
    logger.info("PDF job status checked id=%s status=%s", job.id, job.status)
    return job.public_data()


@app.get("/api/jobs/{job_id}/download")
async def download_job(job_id: str) -> FileResponse:
    job = app.state.jobs.get(job_id)
    if job is None or job.status != "completed" or not job.output_path.is_file():
        logger.warning("PDF download rejected id=%s reason=unavailable", job_id)
        raise HTTPException(status_code=404, detail="This compressed PDF is no longer available.")
    stem = Path(job.filename).stem or "document"
    logger.info("PDF download served id=%s output_bytes=%s", job.id, job.output_size)
    return FileResponse(
        path=job.output_path,
        media_type="application/pdf",
        filename=f"compressed-{stem}.pdf",
        headers={"X-Content-Type-Options": "nosniff"},
    )
