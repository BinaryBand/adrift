import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.utils.progress import Callback

Segment = tuple[float, float]

MIN_LENGTH = 0.1  # seconds

_FFMPEG_BASE = ["ffmpeg", "-hide_banner", "-loglevel", "error"]

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".mp4", ".opus"}


def _duration_weights(part_count: int) -> tuple[int, ...] | None:
    weights_map: dict[int, tuple[int, ...]] = {
        1: (1,),
        2: (60, 1),
        3: (3600, 60, 1),
    }
    return weights_map.get(part_count)


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
    assert res.stdout is not None, "ffprobe returned no output"
    return res.stdout


def _parse_ffprobe_duration(stdout: str) -> float:
    data = json.loads(stdout)
    duration = data.get("format", {}).get("duration")
    assert duration is not None, "No duration in ffprobe output"
    return float(duration)


def _concat_command(concat: Path, dest: Path) -> list[str]:
    return _FFMPEG_BASE + [
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat),
        "-c:a",
        "copy",
        "-y",
        str(dest),
    ]


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


def parse_duration(duration_str: str | None) -> float | None:
    """Parse duration string in HH:MM:SS or MM:SS format to total seconds."""
    if duration_str is None or duration_str == "":
        return None

    parts = duration_str.split(":")
    if weights := _duration_weights(len(parts)):
        return sum(weight * float(part) for weight, part in zip(weights, parts))

    print(f"WARNING: Unrecognized duration format: {duration_str}")
    return None


def get_duration(file: Path) -> float | None:
    assert os.path.exists(file), f"File not found: {file}"

    try:
        return _parse_ffprobe_duration(_run_ffprobe(file))

    except subprocess.CalledProcessError as e:
        print(f"WARNING: ffprobe failed for {file}: exit code {e.returncode}")
        return None
    except Exception as e:
        print(f"WARNING: Failed to get duration for {file}: {e}")
        return None


def invert_segments(file: Path, segments: list[Segment]) -> list[Segment]:
    prev_end = 0.0
    content_segments: list[Segment] = []
    for seg in segments:
        content_segments.append((prev_end, seg[0]))
        prev_end = seg[1]

    total_len = get_duration(file)
    assert total_len is not None, f"Could not get duration for {file}"

    content_segments.append((prev_end, total_len))
    return content_segments


def _extract_segment(file: Path, start: float, duration: float, dest: Path) -> None:
    """Extract one time-bounded segment from a source file."""
    cmd = _FFMPEG_BASE + [
        "-i",
        str(file),
        "-ss",
        str(start),
        "-t",
        str(duration),
        "-y",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _write_concat_list(segment_files: list[Path]) -> Path:
    """Write an ffmpeg concat-list file alongside the first segment."""
    concat = segment_files[0].parent / "concat.txt"
    with open(concat, "w", encoding="utf-8") as f:
        for seg_file in segment_files:
            f.write(f"file '{seg_file.absolute().as_posix()}'\n")
    return concat


def _concat_segment_files(segment_files: list[Path], dest: Path, source_file: Path) -> None:
    """Concatenate extracted segments into a single output file."""
    if len(segment_files) == 1:
        shutil.copy(segment_files[0], dest)
        return
    concat = _write_concat_list(segment_files)
    cmd = _concat_command(concat, dest)
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except Exception as e:
        if isinstance(e, subprocess.CalledProcessError):
            raise handle_subprocess_error(e, cmd, source_file)
        raise RuntimeError(f"Failed to concat segments for {source_file}: {e}")


def _extract_all_segments(
    keep_segs: list[Segment], file: Path, temp_path: Path, callback: Callback | None
) -> list[Path]:
    """Extract every keep segment to individual temp files."""
    segment_files: list[Path] = []
    for i, (start, end) in enumerate(keep_segs):
        seg_file = temp_path / f"seg_{i:04d}{file.suffix}"
        _extract_segment(file, start, end - start, seg_file)
        segment_files.append(seg_file)
        if callback:
            callback(i + 1, len(keep_segs))
    return segment_files


def _cut_segments(
    file: Path,
    segments: list[Segment],
    dest: Path,
    callback: Callback | None = None,
) -> None:
    """Cut segments using re-encoding (slower but no artifacts at join points)."""
    keep_segs = [(s, e) for s, e in invert_segments(file, segments) if e - s >= MIN_LENGTH]
    with tempfile.TemporaryDirectory() as temp_dir:
        seg_files = _extract_all_segments(keep_segs, file, Path(temp_dir), callback)
        _concat_segment_files(seg_files, dest, file)
        if callback and len(seg_files) > 1:
            callback(len(keep_segs), len(keep_segs))


def cut_segments(
    file: Path,
    segments: list[Segment],
    dest: Path | None = None,
    callback: Callback | None = None,
) -> None:
    """Cut segments from audio file."""
    if dest is None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp) / file.name
            _cut_segments(file, segments, temp_path, callback=callback)
            file.unlink(missing_ok=True)
            shutil.move(str(temp_path), str(file))
    else:
        _cut_segments(file, segments, dest, callback=callback)


def _ensure_audio_stream(check_file: Path) -> str:
    """Run ffprobe and ensure the file contains an audio stream; return ffprobe JSON string.

    Raises a RuntimeError with ffprobe output on failure.
    """
    ffprobe_out = _run_ffprobe(check_file)
    data = json.loads(ffprobe_out)
    streams = data.get("streams", [])
    if not any(s.get("codec_type") == "audio" for s in streams):
        raise RuntimeError(f"No audio stream found in {check_file}\nffprobe: {ffprobe_out}")
    return ffprobe_out


def _run_ffmpeg_convert(cmd: list[str], file: Path, output: Path, ffprobe_out: str) -> None:
    """Run ffmpeg conversion command and raise a RuntimeError with stderr on failure."""
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else "No error"
        raise RuntimeError(
            f"ffmpeg failed to convert {file} to opus\n"
            f"Command: {' '.join(cmd)}\n"
            f"Exit code: {e.returncode}\n"
            f"Error output: {stderr}\n"
            f"ffprobe: {ffprobe_out if ffprobe_out else 'no ffprobe output'}"
        ) from e
    


def _extract_stream_bitrate_kbps(ffprobe_out: str) -> int | None:
    """Return the first audio stream bitrate in kbps, or None if unknown."""
    data = _parse_ffprobe_json(ffprobe_out)
    return _get_bitrate_from_data(data)


def _decide_final_bitrate(
    src_kbps: int | None, target_bitrate_kbps: int | None, force_bitrate: bool
) -> int | None:
    """Return final bitrate (kbps) to pass to ffmpeg, or None to use default."""
    if target_bitrate_kbps is None:
        return None
    if src_kbps is not None and not force_bitrate:
        return min(src_kbps, target_bitrate_kbps)
    return target_bitrate_kbps


def _build_opus_cmd(src: Path, dest: Path, bitrate_kbps: int | None = None) -> list[str]:
    """Return an ffmpeg command list for converting src to Opus at dest.

    If `bitrate_kbps` is provided it is passed to ffmpeg as `-b:a {bitrate}k`.
    Otherwise a sensible default of 128k is used.
    """
    cmd = _FFMPEG_BASE + [
        "-i",
        str(src),
        "-vn",
        "-map",
        "0:a",
        "-c:a",
        "libopus",
    ]
    if bitrate_kbps is not None:
        cmd += ["-b:a", f"{bitrate_kbps}k"]
    else:
        cmd += ["-b:a", "128k"]
    cmd += ["-y", str(dest)]
    return cmd


def _parse_ffprobe_json(ffprobe_out: str) -> dict | None:
    try:
        return json.loads(ffprobe_out)
    except Exception:
        return None


def _kbps_from_br(br: object) -> int | None:
    if br is None:
        return None
    try:
        return int(round(int(br) / 1000))
    except Exception:
        return None


def _get_bitrate_from_data(data: dict | None) -> int | None:
    if not isinstance(data, dict):
        return None

    streams = data.get("streams", [])
    for s in streams:
        if s.get("codec_type") == "audio":
            kbps = _kbps_from_br(s.get("bit_rate"))
            if kbps is not None:
                return kbps

    return _kbps_from_br(data.get("format", {}).get("bit_rate"))


def _format_bytes(num: int) -> str:
    """Return human-readable file size string for `num` bytes."""
    try:
        n = float(num)
    except Exception:
        return "0B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0:
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"


def _file_size_or_none(p: Path) -> int | None:
    try:
        return p.stat().st_size
    except Exception:
        return None


def _log_space_change(src: Path, dest: Path) -> None:
    """Log the change in file size between `src` and `dest` (human-readable)."""
    original_size = _file_size_or_none(src)
    new_size = _file_size_or_none(dest)

    if original_size is None or new_size is None:
        print(f"Converted {src} -> {dest}: size info unavailable")
        return

    diff = original_size - new_size
    if diff >= 0:
        print(f"Converted {src} -> {dest}: saved {_format_bytes(diff)} ({diff} bytes)")
    else:
        print(f"Converted {src} -> {dest}: increased size by {_format_bytes(-diff)} ({-diff} bytes)")


def _determine_final_bitrate_for_file(
    file: Path, target_bitrate_kbps: int | None, force_bitrate: bool
) -> tuple[int | None, str]:
    ffprobe_out = _ensure_audio_stream(file)
    src_kbps = _extract_stream_bitrate_kbps(ffprobe_out)
    final_bitrate = _decide_final_bitrate(src_kbps, target_bitrate_kbps, force_bitrate)
    return final_bitrate, ffprobe_out


def convert_to_opus(file: Path, target_bitrate_kbps: int | None = None, force_bitrate: bool = False) -> Path:
    """Convert `file` to Opus and return the new Path."""
    output = file.with_suffix(".opus")
    if file.suffix.lower() == ".opus":
        return file

    final_bitrate, ffprobe_out = _determine_final_bitrate_for_file(
        file, target_bitrate_kbps, force_bitrate
    )

    cmd = _build_opus_cmd(file, output, final_bitrate)
    _run_ffmpeg_convert(cmd, file, output, ffprobe_out)

    # log size change in a helper to keep this function small
    _log_space_change(file, output)

    return output
