from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class CompressionError(RuntimeError):
    """An error that can be shown safely to someone uploading a file."""


class ImageTooLargeError(CompressionError):
    """An image exceeds the decoded-pixel limit."""


@dataclass(frozen=True)
class CompressionOutcome:
    output_size: int
    target_met: bool | None
    message: str
    output_format: str = "pdf"


PROFILES = (
    (150, 82, 300),
    (120, 78, 240),
    (96, 70, 150),
    (72, 60, 120),
    (50, 45, 96),
    (36, 30, 72),
)
COMMAND_TIMEOUT_SECONDS = 240
MAX_IMAGE_PIXELS = 40_000_000
IMAGE_SIGNATURES = {
    "jpeg": b"\xff\xd8\xff",
    "png": b"\x89PNG\r\n\x1a\n",
    "webp": b"RIFF",
}


def inspect_image(source_path: Path) -> tuple[str, int, int]:
    with source_path.open("rb") as source:
        header = source.read(12)
        if header.startswith(IMAGE_SIGNATURES["jpeg"]):
            image_format = "jpeg"
            dimensions = _jpeg_dimensions(source)
        elif header.startswith(IMAGE_SIGNATURES["png"]):
            image_format = "png"
            dimensions = _png_dimensions(source)
        elif header[:4] == IMAGE_SIGNATURES["webp"] and header[8:12] == b"WEBP":
            image_format = "webp"
            dimensions = _webp_dimensions(source)
        else:
            raise CompressionError("Choose a static JPG, PNG, or WebP image.")

    if dimensions is None:
        raise CompressionError("This image is damaged or has an unsupported format.")
    width, height = dimensions
    if width < 1 or height < 1:
        raise CompressionError("This image is damaged or has an unsupported format.")
    if width * height > MAX_IMAGE_PIXELS:
        raise ImageTooLargeError("This image is too large to process. Choose one up to 40 megapixels.")
    return image_format, width, height


def _jpeg_dimensions(source) -> tuple[int, int] | None:
    source.seek(2)
    start_of_frame = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    while marker := source.read(1):
        if marker != b"\xff":
            continue
        while (marker := source.read(1)) == b"\xff":
            pass
        if not marker:
            return None
        marker_code = marker[0]
        if marker_code in {0x00, 0xD8, 0xD9, 0x01, *range(0xD0, 0xD8)}:
            continue
        length_bytes = source.read(2)
        if len(length_bytes) != 2:
            return None
        segment_length = int.from_bytes(length_bytes, "big")
        if segment_length < 2:
            return None
        if marker_code in start_of_frame:
            frame = source.read(5)
            if len(frame) != 5:
                return None
            height = int.from_bytes(frame[1:3], "big")
            width = int.from_bytes(frame[3:5], "big")
            return width, height
        source.seek(segment_length - 2, 1)
    return None


def _png_dimensions(source) -> tuple[int, int] | None:
    source.seek(16)
    dimensions = source.read(8)
    if len(dimensions) != 8:
        return None
    width = int.from_bytes(dimensions[:4], "big")
    height = int.from_bytes(dimensions[4:], "big")
    return width, height


def _webp_dimensions(source) -> tuple[int, int] | None:
    source.seek(12)
    while chunk_header := source.read(8):
        if len(chunk_header) != 8:
            return None
        chunk_type = chunk_header[:4]
        chunk_size = int.from_bytes(chunk_header[4:], "little")
        data_start = source.tell()
        if chunk_type == b"ANIM" or chunk_type == b"ANMF":
            raise CompressionError("Animated WebP files aren’t supported yet.")
        if chunk_type == b"VP8X":
            data = source.read(10)
            if len(data) != 10:
                return None
            if data[0] & 0x02:
                raise CompressionError("Animated WebP files aren’t supported yet.")
            width = 1 + int.from_bytes(data[4:7], "little")
            height = 1 + int.from_bytes(data[7:10], "little")
            return width, height
        if chunk_type == b"VP8 ":
            data = source.read(10)
            if len(data) != 10 or data[3:6] != b"\x9d\x01\x2a":
                return None
            width = int.from_bytes(data[6:8], "little") & 0x3FFF
            height = int.from_bytes(data[8:10], "little") & 0x3FFF
            return width, height
        if chunk_type == b"VP8L":
            data = source.read(5)
            if len(data) != 5 or data[0] != 0x2F:
                return None
            width = 1 + data[1] + ((data[2] & 0x3F) << 8)
            height = 1 + (data[2] >> 6) + (data[3] << 2) + ((data[4] & 0x0F) << 10)
            return width, height
        source.seek(data_start + chunk_size + (chunk_size & 1))
    return None


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


def compress_image(
    source_path: Path,
    output_path: Path,
    target_bytes: int | None,
    output_format: str = "source",
) -> CompressionOutcome:
    source_format, _, _ = inspect_image(source_path)
    if output_format == "source":
        output_format = source_format
    if output_format not in {"jpeg", "png", "webp"}:
        raise CompressionError("Choose JPEG, PNG, or WebP as the output format.")

    original_size = source_path.stat().st_size
    if output_format == "webp":
        _encode_webp(source_path, output_path, source_format, target_bytes)
    else:
        _encode_image_magick(source_path, output_path, output_format, target_bytes)

    output_size = output_path.stat().st_size
    target_met = output_size <= target_bytes if target_bytes is not None else None
    if target_met is False:
        if source_format == output_format and original_size <= target_bytes:
            shutil.copyfile(source_path, output_path)
            return CompressionOutcome(
                output_size=original_size,
                target_met=True,
                message="This image already meets the size limit, so we kept the original.",
                output_format=output_format,
            )
        return CompressionOutcome(
            output_size=output_size,
            target_met=False,
            message="We couldn’t reach the selected size limit. Try a larger limit.",
            output_format=output_format,
        )
    if output_size >= original_size and source_format == output_format:
        shutil.copyfile(source_path, output_path)
        return CompressionOutcome(
            output_size=original_size,
            target_met=original_size <= target_bytes if target_bytes is not None else None,
            message=(
                "This image already meets the size limit, so we kept the original."
                if target_bytes is not None
                else "This image was already optimized, so we kept the original."
            ),
            output_format=output_format,
        )
    return CompressionOutcome(
        output_size=output_size,
        target_met=target_met,
        message=(
            f"Your image is ready in {output_format.upper()} format."
            if output_size >= original_size
            else "Your image is compressed and ready to download."
        ),
        output_format=output_format,
    )


def _encode_webp(
    source_path: Path,
    output_path: Path,
    source_format: str,
    target_bytes: int | None,
) -> None:
    cwebp = shutil.which("cwebp")
    if cwebp is None:
        raise CompressionError("cwebp is missing from this server. Install the WebP tools and try again.")

    command = [cwebp, "-quiet", "-low_memory", "-mt", "-metadata", "exif,icc"]
    if target_bytes is None:
        if source_format == "png":
            command.extend(["-lossless", "-z", "6"])
        else:
            command.extend(["-q", "80"])
    else:
        command.extend(["-size", str(target_bytes), "-pass", "10"])
    command.extend([str(source_path), "-o", str(output_path)])
    _run_image_command(command)
    if not output_path.is_file():
        raise CompressionError("This image couldn’t be read. Choose a static JPG, PNG, or WebP image.")


def _encode_image_magick(
    source_path: Path,
    output_path: Path,
    output_format: str,
    target_bytes: int | None,
) -> None:
    magick = shutil.which("magick")
    convert = shutil.which("convert")
    executable = magick or convert
    if executable is None:
        raise CompressionError(
            "ImageMagick is missing from this server. Install it to export JPEG or PNG."
        )
    command_prefix = [executable]
    extension = ".jpg" if output_format == "jpeg" else ".png"
    qualities = (
        (82, 68, 54, 40, 26, 12)
        if output_format == "jpeg" and target_bytes is not None
        else (82,)
    )
    best_size: int | None = None
    best_path: Path | None = None

    for quality in qualities:
        candidate_path = output_path.parent / f"candidate-{output_format}-{quality}{extension}"
        command = [*command_prefix, str(source_path), "-auto-orient"]
        if output_format == "jpeg":
            command.extend(["-background", "white", "-alpha", "remove", "-alpha", "off", "-quality", str(quality)])
        else:
            command.extend([
                "-define", "png:compression-level=9",
                "-define", "png:compression-filter=5",
            ])
        command.append(str(candidate_path))
        _run_image_command(command)
        if not candidate_path.is_file():
            raise CompressionError("This image couldn’t be read. Choose a static JPG, PNG, or WebP image.")
        candidate_size = candidate_path.stat().st_size
        if best_size is None or candidate_size < best_size:
            best_size = candidate_size
            best_path = candidate_path
        if target_bytes is not None and candidate_size <= target_bytes:
            best_path = candidate_path
            best_size = candidate_size
            break

    if best_path is None or best_size is None:
        raise CompressionError("This image couldn’t be read. Choose a static JPG, PNG, or WebP image.")
    shutil.copyfile(best_path, output_path)


def _run_image_command(command: list[str]) -> None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CompressionError("Image compression took too long. Try a smaller image.") from exc
    except OSError as exc:
        raise CompressionError("The image compression tool could not start. Check the server installation.") from exc

    if result.returncode != 0:
        raise CompressionError("This image couldn’t be read. Choose a static JPG, PNG, or WebP image.")
