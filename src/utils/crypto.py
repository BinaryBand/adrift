from diskcache import Cache
from pathlib import Path
import subprocess
import functools
import hashlib
import os


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


def get_audio_content_hash(file_path: Path, sample_rate: int = 8000) -> str:
    cache = _crypto_cache()
    modified_date = os.path.getmtime(file_path)

    cache_key = f"audio_hash:file={file_path.absolute().as_posix()},mod={modified_date},sr={sample_rate}"
    if (cached_hash := cache.get(cache_key)) is not None:
        return cached_hash

    # Content-normalized hashing: decode small PCM windows and hash them.
    # This avoids decoding the entire file to raw PCM, which is very slow.
    def _get_duration_seconds(path: Path) -> float | None:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        try:
            res = subprocess.run(
                cmd,
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

    duration = _get_duration_seconds(file_path)
    num_samples = 5
    sample_window_seconds = 0.75

    hash_md5 = hashlib.md5()

    try:
        if duration is None or duration <= 0:
            # Fallback: sample from the beginning only.
            sample_times = [0.0]
        else:
            # Evenly distributed sample start times, avoiding the very end.
            usable = max(0.0, duration - sample_window_seconds)
            sample_times = [
                (usable * (i + 1) / (num_samples + 1)) for i in range(num_samples)
            ]

        for t in sample_times:
            cmd = [
                "ffmpeg",
                "-ss",
                f"{t:.3f}",
                "-t",
                f"{sample_window_seconds:.3f}",
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
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            if res.stdout:
                hash_md5.update(res.stdout)
    except Exception:
        # Last-resort fallback: hash raw file bytes (includes metadata).
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)

    hex_hash = hash_md5.hexdigest()
    cache.set(cache_key, hex_hash)
    return hex_hash
