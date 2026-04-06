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
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(file)]
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


def _concat_segment_files(
    segment_files: list[Path], dest: Path, source_file: Path
) -> None:
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
    keep_segs = [
        (s, e) for s, e in invert_segments(file, segments) if e - s >= MIN_LENGTH
    ]
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


def convert_to_opus(file: Path) -> Path:
    """Convert audio file to Opus format (libopus 128k).

    Converts the input file to Opus in the same directory.

    Args:
        file: Path to the audio file to convert.

    Returns:
        Path to the newly created .opus file.

    Raises:
        subprocess.CalledProcessError: If ffmpeg conversion fails.
    """
    output = file.with_suffix(".opus")
    cmd = _FFMPEG_BASE + [
        "-i",
        str(file),
        "-c:a",
        "libopus",
        "-b:a",
        "128k",
        "-y",
        str(output),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output
