from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class CompressionError(RuntimeError):
    """An error that can be shown safely to the person uploading a PDF."""


@dataclass(frozen=True)
class CompressionOutcome:
    output_size: int
    target_met: bool | None
    message: str


PROFILES = (
    (150, 82, 300),
    (120, 78, 240),
    (96, 70, 150),
    (72, 60, 120),
    (50, 45, 96),
    (36, 30, 72),
)
COMMAND_TIMEOUT_SECONDS = 240


def _run_command(command: list[str], error_message: str) -> None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CompressionError(
            "Compression took too long. Try a smaller PDF."
        ) from exc
    except OSError as exc:
        raise CompressionError(
            "A PDF processing tool could not start. Check the server installation."
        ) from exc

    if result.returncode != 0:
        raise CompressionError(error_message)


def compress_pdf(
    source_path: Path,
    output_path: Path,
    target_bytes: int | None,
) -> CompressionOutcome:
    qpdf = shutil.which("qpdf")
    if qpdf is None:
        raise CompressionError("qpdf is missing from this server. Install qpdf and try again.")

    _run_command(
        [qpdf, "--check", str(source_path)],
        "This PDF may be password-protected or damaged. Remove its password or try another PDF.",
    )

    original_size = source_path.stat().st_size
    if target_bytes is not None and original_size <= target_bytes:
        shutil.copyfile(source_path, output_path)
        return CompressionOutcome(
            output_size=original_size,
            target_met=True,
            message="Your PDF already meets this size target, so we kept the original unchanged.",
        )

    ghostscript = shutil.which("gs")
    if ghostscript is None:
        raise CompressionError(
            "Ghostscript is missing from this server. Install Ghostscript and try again."
        )

    profiles = PROFILES if target_bytes is not None else PROFILES[:1]
    best_size = original_size

    for index, (resolution, quality, mono_resolution) in enumerate(profiles):
        compressed_path = output_path.parent / f"compressed-{index}.pdf"
        linearized_path = output_path.parent / f"linearized-{index}.pdf"
        _run_command(
            [
                ghostscript,
                "-q",
                "-dSAFER",
                "-dBATCH",
                "-dNOPAUSE",
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.5",
                "-dPDFSETTINGS=/ebook",
                "-dDetectDuplicateImages=true",
                "-dCompressFonts=true",
                "-dDownsampleColorImages=true",
                f"-dColorImageResolution={resolution}",
                "-dColorImageDownsampleType=/Bicubic",
                "-dDownsampleGrayImages=true",
                f"-dGrayImageResolution={resolution}",
                "-dGrayImageDownsampleType=/Bicubic",
                "-dDownsampleMonoImages=true",
                f"-dMonoImageResolution={mono_resolution}",
                "-dPassThroughJPEGImages=false",
                f"-sOutputFile={compressed_path}",
                "-c",
                (
                    f"<</ColorImageDict << /QFactor {quality / 100:.2f} /Blend 1 "
                    "/HSamples [2 1 1 2] /VSamples [2 1 1 2] >> "
                    f"/GrayImageDict << /QFactor {quality / 100:.2f} /Blend 1 "
                    "/HSamples [2 1 1 2] /VSamples [2 1 1 2] >> >> setdistillerparams"
                ),
                "-f",
                str(source_path),
            ],
            "Ghostscript could not compress this PDF. It may be password-protected or damaged.",
        )
        _run_command(
            [
                qpdf,
                "--linearize",
                "--object-streams=generate",
                str(compressed_path),
                str(linearized_path),
            ],
            "qpdf could not prepare the compressed PDF. Try another file.",
        )
        _run_command(
            [qpdf, "--check", str(linearized_path)],
            "The compressed PDF did not pass validation. Try another file.",
        )

        candidate_size = linearized_path.stat().st_size
        if candidate_size < best_size:
            shutil.copyfile(linearized_path, output_path)
            best_size = candidate_size

        if target_bytes is not None and candidate_size <= target_bytes:
            break

    if not output_path.exists():
        shutil.copyfile(source_path, output_path)

    output_size = output_path.stat().st_size
    target_met = output_size <= target_bytes if target_bytes is not None else None
    if target_met:
        message = "Your PDF meets the selected size target."
    elif target_bytes is not None:
        message = "We couldn't reach the selected size target. This is the smallest version we could make."
    elif output_size < original_size:
        message = "Compression is complete. Your PDF is smaller."
    else:
        message = "This PDF was already optimized, so we kept the original file."

    return CompressionOutcome(
        output_size=output_size,
        target_met=target_met,
        message=message,
    )
