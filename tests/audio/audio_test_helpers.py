"""
Helpers for audio processing tests.
Generates a short synthetic audio file using ffmpeg (no network required).
"""

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.files.audio import MIN_LENGTH

OUTPUT_DIR = "tests/resources"
OUTPUT_FILE = Path(OUTPUT_DIR) / "test_audio.mp3"

# 65 seconds: long enough for all segment tests (which go up to t=60)
_DURATION = 65


def duration_matches(expected: float = 0, actual: float = 0, tolerance: float = 0.2) -> bool:
    """Check if actual duration matches expected within a tolerance percentage."""
    diff = float(actual or MIN_LENGTH) / float(expected or MIN_LENGTH)
    return abs(1 - diff) <= tolerance


def download_test_audio() -> Path:
    """Return a short synthetic MP3 suitable for audio processing tests.

    Generated locally via ffmpeg (sine wave) — no network access required.
    The file is cached in tests/resources/ and reused across runs.
    """
    if OUTPUT_FILE.exists():
        return OUTPUT_FILE

    if shutil.which("ffmpeg") is None:
        raise unittest.SkipTest("ffmpeg not found; skipping audio tests")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={_DURATION}",
        "-ar",
        "44100",
        "-b:a",
        "128k",
        "-y",
        str(OUTPUT_FILE),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return OUTPUT_FILE
    except subprocess.CalledProcessError:
        raise unittest.SkipTest("ffmpeg failed to generate test audio; skipping audio tests")


if __name__ == "__main__":
    download_test_audio()
