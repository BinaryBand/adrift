from scipy.spatial.distance import cosine, euclidean
from scipy.signal import spectrogram
from cachetools import LRUCache
from diskcache import Cache
from pathlib import Path

import numpy as np
import subprocess
import tempfile
import shutil
import json
import sys
import os


sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.utils.crypto import get_file_hash
from src.utils.progress import Callback
from src.utils.regex import re_compile


_NOISE_DB = -30  # dB
_SAMPLE_RATE = 8000  # Hz

LAX_SIMILARITY = 0.9999
LAX_EUCLIDEAN = 0.8
STRICT_SIMILARITY = 0.99999
STRICT_EUCLIDEAN = 0.5

_MAX_CACHED_FILES = 4
_FULL_AUDIO_CACHE: LRUCache = LRUCache(maxsize=_MAX_CACHED_FILES)
_FEATS_CACHE = Cache(".cache/feats")
_SILENCE_CACHE = Cache(".cache/silence")


Segment = tuple[float, float]
FeatArgs = tuple[float, float, Path]

MIN_LENGTH = 0.1  # seconds
MIN_AD_LENGTH = 10  # seconds
MIN_BLOCK_LENGTH = 25  # seconds

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


def _trim_audio_silence(audio_data: np.ndarray) -> np.ndarray:
    """Trim leading and trailing silence from audio data based on a dB threshold."""
    if audio_data.size == 0:
        return np.array([])

    threshold = 10 ** (_NOISE_DB / 20) * np.max(np.abs(audio_data))
    above = np.where(np.abs(audio_data) >= threshold)[0]

    if above.size == 0:
        return np.array([])

    start_index = above[0]
    end_index = above[-1] + 1

    return audio_data[start_index:end_index]


def _get_feats(file: Path, start: float | None, end: float | None) -> np.ndarray:
    key = str(file)

    if key in _FULL_AUDIO_CACHE:
        full = _FULL_AUDIO_CACHE[key]
        if start is None and end is None:
            return full.copy()

        start_sample = int((start or 0.0) * _SAMPLE_RATE)
        end_sample = int((end or (len(full) / _SAMPLE_RATE)) * _SAMPLE_RATE)
        return full[start_sample:end_sample].copy()

    cmd = [
        "ffmpeg",
        "-i",
        key,
        "-f",
        "s16le",
        "-ac",
        "1",
        "-ar",
        str(_SAMPLE_RATE),
        "-",
    ]

    if start is not None:
        cmd[1:1] = ["-ss", str(start)]
    if end is not None:
        cmd[1:1] = ["-to", str(end)]

    try:
        res = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
        )

        raw_data = np.frombuffer(res.stdout, dtype=np.int16).astype(np.float32)
        if start is None and end is None:
            _FULL_AUDIO_CACHE[key] = raw_data

        return raw_data

    except Exception as e:
        if isinstance(e, subprocess.CalledProcessError):
            raise handle_subprocess_error(e, cmd, file)
        raise RuntimeError(f"Failed to concat segments for {file}: {e}")


def calc_feat_distance(lhs: np.ndarray, rhs: np.ndarray) -> tuple[float, float]:
    """Calculate cosine similarity and euclidean distance between two segments"""
    if len(lhs) == 0 or len(rhs) == 0:
        return 0.0, float("inf")

    max_len = max(len(lhs), len(rhs))
    if len(lhs) < max_len:
        lhs = np.pad(lhs, (0, max_len - len(lhs)))
    if len(rhs) < max_len:
        rhs = np.pad(rhs, (0, max_len - len(rhs)))

    cos_sim = 1 - cosine(lhs, rhs)
    eucl_dist = euclidean(lhs, rhs)
    return cos_sim, eucl_dist


def get_feats(
    file: Path, start: float | None = None, end: float | None = None
) -> np.ndarray:
    file_hash = get_file_hash(file)

    cache_key = f"audio_feat:{file_hash}:start={start},end={end}"
    if (cached := _FEATS_CACHE.get(cache_key)) is not None:
        return cached

    audio_data = _get_feats(file, start, end)
    if audio_data.size == 0:
        feature = np.array([])
    else:
        audio_data = audio_data / (np.max(np.abs(audio_data)) + 1e-6)  # Normalize

        # SciPy will clamp nperseg to len(audio_data) if the sample is short.
        # If noverlap is not also clamped, it can raise:
        #   ValueError: noverlap must be less than nperseg
        if audio_data.size < 2:
            feature = np.array([])
        else:
            nperseg = min(256, int(audio_data.size))
            noverlap = min(128, max(0, nperseg - 1))

            _, _, Sxx = spectrogram(
                audio_data, _SAMPLE_RATE, nperseg=nperseg, noverlap=noverlap
            )
            feats = np.log(np.abs(Sxx) + 1e-6)
            feature_vector = np.mean(feats, axis=1)
            feature = _trim_audio_silence(feature_vector)

    _FEATS_CACHE.set(cache_key, feature)
    return feature


def prefetch_full_audio(file: Path) -> None:
    """Decode and cache the full audio stream in memory.

    This lets subsequent windowed `get_feats(file, start, end)` calls slice from
    the cached raw audio instead of re-running ffmpeg each time.

    Note: for very long files this can use substantial RAM.
    """
    _get_feats(file, None, None)


def find_silent_segments(file: Path) -> list[Segment]:
    assert os.path.exists(file), f"Audio file does not exist: {file}"

    file_hash = get_file_hash(file)
    cache_key = f"silence:{file_hash}:noise={_NOISE_DB}:min={MIN_LENGTH}"
    if (cached := _SILENCE_CACHE.get(cache_key)) is not None:
        return cached

    detect = f"silencedetect=noise={_NOISE_DB}dB:duration={MIN_LENGTH}"
    cmd = ["ffmpeg", "-i", str(file), "-af", detect, "-f", "null", "-"]

    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )

        start_pattern = re_compile(r"silence_start: ([\d.]+)")
        end_pattern = re_compile(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)")
        starts = [float(x) for x in start_pattern.findall(res.stderr)]
        ends = [float(end) for end, _ in end_pattern.findall(res.stderr)]

        silence_segments: list[Segment] = []
        for start, end in zip(starts, ends):
            silence_segments.append((round(start, 2), round(end, 2)))

        _SILENCE_CACHE.set(cache_key, silence_segments)
        return silence_segments

    except Exception as e:
        if isinstance(e, subprocess.CalledProcessError):
            raise handle_subprocess_error(e, cmd, file)
        raise RuntimeError(f"Failed to concat segments for {file}: {e}")


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
        seconds = int(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    elif len(parts) == 2:
        minutes = int(parts[0])
        seconds = int(parts[1])
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


def extract_segment(file: Path, start: float, end: float, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.unlink(missing_ok=True)

    # Handle invalid time range - create empty file instead of calling ffmpeg
    if end <= start:
        print(
            f"WARNING: Invalid time range: start={start}, end={end}. Creating empty file."
        )
        dest.touch()
        return dest

    end -= start
    base = [
        "ffmpeg",
        "-i",
        str(file),
        "-ss",
        str(start),
        "-t",
        str(end),
        "-y",
        str(dest),
    ]
    strategies = [base, base + ["-c", "copy"]]

    errors: list[Exception] = []
    for cmd in strategies:
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return dest
        except subprocess.CalledProcessError as e:
            errors.append(e)
            # Try next strategy
            continue
        except Exception as e:
            errors.append(e)
            continue

    # If all strategies failed, re-raise the first CalledProcessError if present
    # This allows tests to catch specific ffmpeg errors
    for error in errors:
        if isinstance(error, subprocess.CalledProcessError):
            raise error

    raise Exception("All strategies failed.", "\n".join(str(e) for e in errors))


# cspell:words libmp3lame asetpts STARTPTS
def copy_segments(
    file: Path,
    segments: list[FeatArgs],
    batch_size: int = 30,
    callback: Callback | None = None,
) -> None:
    segments = [s for s in segments.copy() if not Path(s[2]).exists()]
    if len(segments) == 0:
        return None

    ext = file.suffix.lower()
    codec = "libmp3lame" if ext == ".mp3" else "aac"

    for h in enumerate(segments[::batch_size]):
        batch = segments[h[0] * batch_size : h[0] * batch_size + batch_size]

        normalized: list[FeatArgs] = []
        for s, e, out in batch:
            if s > e:
                s, e = e, s
            normalized.append((s, e, out))
        normalized.sort(key=lambda x: x[0])

        filters = []
        maps = []

        begin = normalized[0][0]
        for i, (start, end, out) in enumerate(normalized):
            rel_start = start - begin
            rel_end = end - begin

            filter = f"[0:a]atrim=start={rel_start:.1f}:end={rel_end:.1f},asetpts=PTS-STARTPTS[a{i}]"
            filters.append(filter)
            maps.append((f"[a{i}]", out))

        filter_complex = "; ".join(filters)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-threads", "0"]
        if begin > 0:
            cmd += ["-ss", str(begin)]
        cmd += ["-i", str(file), "-vn", "-filter_complex", filter_complex]
        for map_spec, out_path in maps:
            cmd += ["-map", map_spec, "-c:a", codec, str(out_path)]
        cmd += ["-y"]
        subprocess.run(cmd, check=True, capture_output=True)

        if callback:
            callback(min((h[0] + 1) * batch_size, len(segments)), len(segments))

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
