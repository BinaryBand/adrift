from pathlib import Path

import subprocess
import tempfile
import shutil
import json
import sys
import os


sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.utils.progress import Callback


Segment = tuple[float, float]

MIN_LENGTH = 0.1  # seconds

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".mp4"}


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


def parse_duration(duration_str: str) -> float | None:
    """Parse duration string in HH:MM:SS or MM:SS format to total seconds."""
    if duration_str is None or duration_str == "":
        return None

    parts = duration_str.split(":")
    if len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    elif len(parts) == 2:
        minutes = int(parts[0])
        seconds = float(parts[1])
        return minutes * 60 + seconds
    elif len(parts) == 1:
        return float(parts[0])

    print(f"WARNING: Unrecognized duration format: {duration_str}")
    return None


def get_duration(file: Path) -> float | None:
    assert os.path.exists(file), f"File not found: {file}"

    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(file)]

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=True,
        )
        assert res.stdout is not None, "ffprobe returned no output"

        data = json.loads(res.stdout)
        duration = data.get("format", {}).get("duration")
        assert duration is not None, "No duration in ffprobe output"

        return float(duration)

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


def _cut_segments(
    file: Path,
    segments: list[Segment],
    dest: Path,
    callback: Callback | None = None,
) -> None:
    """Cut segments using re-encoding (slower but no artifacts at join points)."""
    keep_segments = invert_segments(file, segments)
    keep_segments = [(s, e) for s, e in keep_segments if e - s >= MIN_LENGTH]

    BASE = ["ffmpeg", "-hide_banner", "-loglevel", "error"]

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        segment_files = []

        # Extract each keep segment with re-encoding for clean cuts
        for i, (start, end) in enumerate(keep_segments):
            segment_file = temp_path / f"seg_{i:04d}{file.suffix}"
            duration = end - start

            cmd = BASE + [
                "-i",
                str(file),
                "-ss",
                str(start),
                "-t",
                str(duration),
                "-y",
                str(segment_file),
            ]

            subprocess.run(cmd, check=True, capture_output=True)
            segment_files.append(segment_file)
            if callback:
                callback(i + 1, len(keep_segments))

        # Concat all segments with re-encoding for seamless joins
        if len(segment_files) == 1:
            shutil.copy(segment_files[0], dest)

        else:
            concat = temp_path / "concat.txt"
            with open(concat, "w", encoding="utf-8") as f:
                for seg_file in segment_files:
                    path_str = seg_file.absolute().as_posix()
                    f.write(f"file '{path_str}'\n")

            cmd = BASE + [
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

            try:
                subprocess.run(cmd, check=True, capture_output=True)

            except Exception as e:
                if isinstance(e, subprocess.CalledProcessError):
                    raise handle_subprocess_error(e, cmd, file)
                raise RuntimeError(f"Failed to concat segments for {file}: {e}")

            if callback:
                callback(len(keep_segments), len(keep_segments))


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
