import functools
import hashlib
import os
import subprocess
from pathlib import Path

from diskcache import Cache


@functools.cache
def _crypto_cache() -> Cache:
    return Cache(".cache/crypto", size_limit=100 * 1024 * 1024)


def get_hash(payload: str) -> str:
    cache = _crypto_cache()

    cache_key = f"hash:pl={payload}"
    if (cached := cache.get(cache_key)) is not None:
        return cached

    hash_md5 = hashlib.md5()
    hash_md5.update(payload.encode("utf-8"))
    hash = hash_md5.hexdigest()

    cache.set(cache_key, hash)
    return hash


def get_file_hash(file_path: Path) -> str:
    cache = _crypto_cache()
    modified_date = os.path.getmtime(file_path)

    cache_key = f"md5:cs={file_path.absolute().as_posix()},mod={modified_date}"
    if (cached_md5 := cache.get(cache_key)) is not None:
        return cached_md5

    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    hex = hash_md5.hexdigest()

    cache.set(cache_key, hex)
    return hex


def sha256(data: str) -> str:
    """Generate SHA-256 hash of the input data."""
    hash_obj = hashlib.sha256(data.encode("utf-8"))
    return hash_obj.hexdigest()


def _build_ffprobe_cmd(path: Path) -> list[str]:
    return [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]


def _probe_duration(path: Path) -> float | None:
    """Return the duration of an audio file in seconds via ffprobe."""
    try:
        res = subprocess.run(
            _build_ffprobe_cmd(path),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        value = (res.stdout or "").strip()
        return float(value) if value else None
    except Exception:
        return None


def _compute_sample_times(
    duration: float | None, num_samples: int, window: float
) -> list[float]:
    """Return evenly-distributed sample start positions across the file."""
    if duration is None or duration <= 0:
        return [0.0]
    usable = max(0.0, duration - window)
    return [(usable * (i + 1) / (num_samples + 1)) for i in range(num_samples)]


def _build_ffmpeg_pcm_cmd(
    file_path: Path, t: float, window: float, sample_rate: int
) -> list[str]:
    return [
        "ffmpeg",
        "-ss",
        f"{t:.3f}",
        "-t",
        f"{window:.3f}",
        "-i",
        str(file_path),
        "-vn",
        "-f",
        "s16le",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-",
    ]


def _hash_audio_samples(
    file_path: Path, sample_times: list[float], window: float, sample_rate: int
) -> hashlib.md5:  # type: ignore[type-arg]
    """Hash PCM windows at each sample position. Returns a partially-filled md5."""
    hash_md5 = hashlib.md5()
    for t in sample_times:
        res = subprocess.run(
            _build_ffmpeg_pcm_cmd(file_path, t, window, sample_rate),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        if res.stdout:
            hash_md5.update(res.stdout)
    return hash_md5


def _fallback_hash_bytes(file_path: Path) -> str:
    """Hash raw file bytes as a last resort (includes container metadata)."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def get_audio_content_hash(file_path: Path, sample_rate: int = 8000) -> str:
    cache = _crypto_cache()
    modified_date = os.path.getmtime(file_path)
    cache_key = f"audio_hash:file={file_path.absolute().as_posix()},mod={modified_date},sr={sample_rate}"
    if (cached_hash := cache.get(cache_key)) is not None:
        return cached_hash

    sample_window = 0.75
    num_samples = 5
    duration = _probe_duration(file_path)
    sample_times = _compute_sample_times(duration, num_samples, sample_window)

    try:
        hex_hash = _hash_audio_samples(
            file_path, sample_times, sample_window, sample_rate
        ).hexdigest()
    except Exception:
        hex_hash = _fallback_hash_bytes(file_path)

    cache.set(cache_key, hex_hash)
    return hex_hash
