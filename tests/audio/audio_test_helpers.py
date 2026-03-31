"""
Script to download a test video for audio testing.
Downloads dQw4w9WgXcQ as MP3 for use in audio processing tests.
"""

from pathlib import Path
import subprocess
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.files.audio import MIN_LENGTH

TEST_VIDEO_ID = "dQw4w9WgXcQ"
OUTPUT_DIR = "tests/resources"
OUTPUT_FILE = Path(OUTPUT_DIR) / f"{TEST_VIDEO_ID}.mp3"


def duration_matches(
    expected: float = 0, actual: float = 0, tolerance: float = 0.2
) -> bool:
    """Check if actual duration matches expected within a tolerance percentage."""
    diff = float(actual or MIN_LENGTH) / float(expected or MIN_LENGTH)
    return abs(1 - diff) <= tolerance


def download_test_audio():
    """Download test video as MP3."""
    if OUTPUT_FILE.exists():
        return OUTPUT_FILE

    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "128K",
        "--output",
        str(OUTPUT_FILE),
        f"https://www.youtube.com/watch?v={TEST_VIDEO_ID}",
    ]

    try:
        subprocess.run(cmd, check=True)
        return OUTPUT_FILE
    except subprocess.CalledProcessError:
        sys.exit(1)


if __name__ == "__main__":
    download_test_audio()
