import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict, Unpack, cast

from adrift.core.util.media import AUDIO_EXTENSIONS
from adrift.core.util.progress import Callback

logger = logging.getLogger(__name__)

_FFMPEG_BASE = ["ffmpeg", "-hide_banner", "-loglevel", "error"]


class OpusConversionKwargs(TypedDict, total=False):
    target_bitrate_kbps: int | None
    force_bitrate: bool
    application: str


@dataclass
class _OpusConversionSettings:
    target_bitrate_kbps: int | None = None
    force_bitrate: bool = False
    application: str = "audio"


def _run_ffprobe(file: Path) -> str:
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(file),
    ]
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=True,
    )
    if not res.stdout:
        msg = "ffprobe returned no output"
        raise ValueError(msg)
    return res.stdout


def _parse_ffprobe_duration(stdout: str) -> float:
    data = json.loads(stdout)
    duration = data.get("format", {}).get("duration")
    if duration is None:
        msg = "No duration in ffprobe output"
        raise ValueError(msg)
    return float(duration)


def handle_subprocess_error(
    e: subprocess.CalledProcessError, cmd: list[str], file: Path
) -> RuntimeError:
    stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else "No error"
    return RuntimeError(
        f"ffmpeg failed to extract audio features from {file}\n"
        f"Command: {' '.join(cmd)}\n"
        f"Exit code: {e.returncode}\n"
        f"Error output: {stderr}"
    )


def is_audio(filename: Path | str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in AUDIO_EXTENSIONS


def get_duration(file: Path) -> float | None:
    if not os.path.exists(file):
        msg = f"File not found: {file}"
        raise FileNotFoundError(msg)

    try:
        return _parse_ffprobe_duration(_run_ffprobe(file))

    except subprocess.CalledProcessError as e:
        logger.warning("ffprobe failed for %s: exit code %s", file, e.returncode)
        return None
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as e:
        logger.warning("Failed to get duration for %s: %s", file, e)
        return None
    except subprocess.CalledProcessError as e:
        logger.warning("ffprobe failed for %s: exit code %s", file, e.returncode)
        return None
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as e:
        logger.warning("Failed to get duration for %s: %s", file, e)
        return None


def _normalize_streams(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a list of stream dicts extracted from ffprobe JSON `data`.

    This normalizes untyped JSON lists into a typed list of dicts so callers
    can inspect stream fields safely.
    """
    streams_raw = data.get("streams")
    if not isinstance(streams_raw, list):
        return []
    contents = cast("list[Any]", streams_raw)
    normalized: list[dict[str, Any]] = []
    for item in contents:
        if isinstance(item, dict):
            normalized.append(cast("dict[str, Any]", item))
    return normalized


def _find_audio_stream(streams: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the first stream dict whose `codec_type` is `audio`.

    Returns None if no such stream is present.
    """
    for s in streams:
        if s.get("codec_type") == "audio":
            return s
    return None


def _ensure_audio_stream(check_file: Path) -> str:
    """Run ffprobe and ensure the file contains an audio stream; return ffprobe JSON string.

    Raises a RuntimeError with ffprobe output on failure.
    """
    ffprobe_out = _run_ffprobe(check_file)
    raw = json.loads(ffprobe_out)
    if not isinstance(raw, dict):
        msg = f"ffprobe did not return JSON dict for {check_file}"
        raise RuntimeError(msg)
    data = cast("dict[str, Any]", raw)
    streams = _normalize_streams(data)
    audio_stream = _find_audio_stream(streams)
    if audio_stream is None:
        msg = f"No audio stream found in {check_file}"
        raise RuntimeError(msg)
    return ffprobe_out


def _run_ffmpeg_convert(cmd: list[str], file: Path, ffprobe_out: str) -> None:
    """Run ffmpeg conversion command and raise a RuntimeError with stderr on failure."""
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else "No error"
        msg = (
            f"ffmpeg failed to convert {file} to opus\n"
            f"Command: {' '.join(cmd)}\n"
            f"Exit code: {e.returncode}\n"
            f"Error output: {stderr}\n"
            f"ffprobe: {ffprobe_out or 'no ffprobe output'}"
        )
        raise RuntimeError(msg) from e


def _run_ffmpeg_convert_with_progress(
    cmd: list[str],
    file: Path,
    ffprobe_out: str,
    callback: Callback,
) -> None:
    progress_cmd = [*_FFMPEG_BASE, "-progress", "pipe:1", "-nostats", *cmd[len(_FFMPEG_BASE) :]]
    total_duration = _parse_ffprobe_duration(ffprobe_out)
    total_seconds = max(int(total_duration), 1)
    return_code, stderr = _run_ffmpeg_progress_process(progress_cmd, total_seconds, callback)

    callback(total_seconds, total_seconds)
    if return_code != 0:
        msg = (
            f"ffmpeg failed to convert {file} to opus\n"
            f"Command: {' '.join(progress_cmd)}\n"
            f"Exit code: {return_code}\n"
            f"Error output: {stderr or 'No error'}\n"
            f"ffprobe: {ffprobe_out or 'no ffprobe output'}"
        )
        raise RuntimeError(msg)


def _run_ffmpeg_progress_process(
    progress_cmd: list[str],
    total_seconds: int,
    callback: Callback,
) -> tuple[int, str]:

    with subprocess.Popen(
        progress_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore",
    ) as process:
        if process.stdout is None:
            msg = "ffmpeg progress stream not available"
            raise RuntimeError(msg)
        for raw_line in process.stdout:
            _maybe_report_ffmpeg_progress(raw_line, total_seconds, callback)

        stderr = process.stderr.read() if process.stderr is not None else ""
        return_code = process.wait()
    return return_code, stderr


def _maybe_report_ffmpeg_progress(
    raw_line: str,
    total_seconds: int,
    callback: Callback,
) -> None:
    if not raw_line.startswith("out_time_us="):
        return
    try:
        current_microseconds = int(raw_line.split("=", 1)[1].strip())
    except ValueError:
        return
    current_seconds = max(current_microseconds // 1_000_000, 0)
    callback(min(current_seconds, total_seconds), total_seconds)


def _build_opus_copy_cmd(src: Path, dest: Path) -> list[str]:
    """Return an ffmpeg command to remux an already-Opus stream into an Ogg container."""
    return [*_FFMPEG_BASE, "-i", str(src), "-vn", "-map", "0:a", "-c:a", "copy", "-y", str(dest)]


def _build_opus_cmd(
    src: Path,
    dest: Path,
    bitrate_kbps: int | None = None,
    application: str = "audio",
) -> list[str]:
    """Return an ffmpeg command list for converting src to Opus at dest."""
    cmd = [
        *_FFMPEG_BASE,
        "-i",
        str(src),
        "-vn",
        "-map",
        "0:a",
        "-c:a",
        "libopus",
        "-application",
        application,
    ]
    if bitrate_kbps is not None:
        cmd += ["-b:a", f"{bitrate_kbps}k"]
    else:
        cmd += ["-b:a", "128k"]
    cmd += ["-y", str(dest)]
    return cmd


def _parse_ffprobe_json(ffprobe_out: str) -> dict[str, Any] | None:
    try:
        raw = json.loads(ffprobe_out)
        if isinstance(raw, dict):
            return cast("dict[str, Any]", raw)
        return None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _kbps_from_br(br: Any) -> int | None:
    if br is None:
        return None
    try:
        result = round(int(br) / 1000)
        return result if result > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _get_bitrate_from_streams(streams: list[dict[str, Any]]) -> int | None:
    """Return the first valid kbps value found in `streams`, or None."""
    for s in streams:
        if s.get("codec_type") == "audio":
            kbps = _kbps_from_br(s.get("bit_rate"))
            if kbps is not None:
                return kbps
    return None


def _get_bitrate_from_data(data: dict[str, Any] | None) -> int | None:
    if not isinstance(data, dict):
        return None

    streams = _normalize_streams(data)
    kbps = _get_bitrate_from_streams(streams)
    if kbps is not None:
        return kbps

    fmt_raw = data.get("format")
    fmt = cast("dict[str, Any]", fmt_raw) if isinstance(fmt_raw, dict) else {}
    return _kbps_from_br(fmt.get("bit_rate"))


def _extract_stream_bitrate_kbps(ffprobe_out: str) -> int | None:
    data = _parse_ffprobe_json(ffprobe_out)
    return _get_bitrate_from_data(data)


def _decide_final_bitrate(
    src_kbps: int | None, target_bitrate_kbps: int | None, force_bitrate: bool
) -> int | None:
    if target_bitrate_kbps is None:
        return None
    if src_kbps is not None and not force_bitrate:
        return min(src_kbps, target_bitrate_kbps)
    return target_bitrate_kbps


def _format_bytes(num: int) -> str:
    try:
        n = float(num)
    except (TypeError, ValueError):
        return "0B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0:
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"


def _file_size_or_none(p: Path) -> int | None:
    try:
        return p.stat().st_size
    except OSError:
        return None


def _log_space_change(src: Path, dest: Path) -> None:
    original_size = _file_size_or_none(src)
    new_size = _file_size_or_none(dest)

    if original_size is None or new_size is None:
        logger.info("Converted %s -> %s: size info unavailable", src, dest)
        return

    diff = original_size - new_size
    if diff >= 0:
        logger.info("Converted %s -> %s: saved %s (%d bytes)", src, dest, _format_bytes(diff), diff)
    else:
        logger.info(
            "Converted %s -> %s: increased size by %s (%d bytes)",
            src,
            dest,
            _format_bytes(-diff),
            -diff,
        )


def _prepare_opus_conversion(
    file: Path,
    settings: _OpusConversionSettings,
) -> tuple[Path, list[str], str]:
    output = file.with_suffix(".opus")
    ffprobe_out = _ensure_audio_stream(file)
    data = _parse_ffprobe_json(ffprobe_out)
    streams = _normalize_streams(data) if isinstance(data, dict) else []
    audio_stream = _find_audio_stream(streams) or {}
    if audio_stream.get("codec_name") == "opus":
        return output, _build_opus_copy_cmd(file, output), ffprobe_out
    src_kbps = _extract_stream_bitrate_kbps(ffprobe_out)
    final_bitrate = _decide_final_bitrate(
        src_kbps,
        settings.target_bitrate_kbps,
        settings.force_bitrate,
    )
    cmd = _build_opus_cmd(file, output, final_bitrate, settings.application)
    return output, cmd, ffprobe_out


def convert_to_opus(
    file: Path,
    callback: Callback | None = None,
    **kwargs: Unpack[OpusConversionKwargs],
) -> Path:
    """Convert `file` to Opus."""
    if file.suffix.lower() == ".opus":
        return file
