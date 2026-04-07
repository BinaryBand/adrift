# ruff: noqa: E402
import sys
from pathlib import Path

import dotenv

sys.path.insert(0, Path(dotenv.find_dotenv()).parent.as_posix())
dotenv.load_dotenv()

import argparse
import subprocess
import tempfile

from tqdm import tqdm

from src.files.s3 import download_file as s3_download_file
from src.files.s3 import get_s3_client

_FFMPEG_BASE = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".mp4"}


def _convert_to_opus(input_path: Path, output_path: Path) -> None:
    """Convert input audio to Opus format using ffmpeg."""
    cmd = _FFMPEG_BASE + [
        "-i",
        str(input_path),
        "-c:a",
        "libopus",
        "-b:a",
        "128k",
        "-y",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _list_all_s3_objects(bucket: str, prefix: str = "") -> list[str]:
    """List all objects under bucket/prefix, handling pagination."""
    client = get_s3_client()
    paginator = client.get_paginator("list_objects_v2")
    page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix)

    keys: list[str] = []
    for page in page_iterator:
        contents = page.get("Contents", [])
        for obj in contents:
            key = obj.get("Key")
            if isinstance(key, str):
                keys.append(key)
    return keys


def _download_convert_save(bucket: str, s3_key: str, local_path: Path, dry_run: bool) -> bool:
    """Download from S3, convert to opus, save locally.

    Returns True on success, False on any error.
    """
    local_path.parent.mkdir(parents=True, exist_ok=True)

    if dry_run:
        print(f"[DRY RUN] {s3_key} → {local_path}")
        return True

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            input_path = tmpdir_path / Path(s3_key).name
            output_path = local_path

            # Download from S3 (with retries)
            s3_download_file(bucket, s3_key, input_path)

            # Convert to opus
            _convert_to_opus(input_path, output_path)

        return True
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else "no stderr"
        print(f"ERROR: ffmpeg failed for {s3_key}: exit {e.returncode}: {stderr}")
        return False
    except Exception as e:
        print(f"ERROR: Failed to process {s3_key}: {e}")
        return False


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download all podcasts from S3 and convert audio to Opus."
    )
    parser.add_argument(
        "dest",
        type=Path,
        help="Local destination directory (e.g. /media/owen/228AF2AB7A2D4C44)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="List files that would be downloaded without making any changes.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of files to process (default: unlimited).",
    )
    return parser.parse_args()


def main() -> None:
    """Main orchestration: list S3 objects, download and convert each."""
    args = _parse_args()
    dest_root = args.dest

    if not args.dry_run and not dest_root.exists():
        dest_root.mkdir(parents=True, exist_ok=True)
        print(f"Created destination directory: {dest_root}")

    # List all objects in media/podcasts prefix
    print("Listing objects from S3...")
    all_keys = _list_all_s3_objects("media", "podcasts/")

    # Filter to audio files only
    audio_keys = [k for k in all_keys if any(k.endswith(ext) for ext in AUDIO_EXTENSIONS)]

    print(f"Found {len(audio_keys)} audio files to process")

    # Apply limit if specified
    if args.limit:
        audio_keys = audio_keys[: args.limit]
        print(f"Limited to {len(audio_keys)} files")

    # Download and convert each file
    successes, errors = 0, 0
    for s3_key in tqdm(audio_keys, desc="Processing audio files"):
        # Construct local path: podcasts/show-name/episode.opus
        local_path = dest_root / Path(s3_key).with_suffix(".opus").as_posix()

        ok = _download_convert_save("media", s3_key, local_path, dry_run=args.dry_run)
        if ok:
            successes += 1
        else:
            errors += 1

    # Summary
    print(f"\nDone. Processed: {successes}, Errors: {errors}")


if __name__ == "__main__":
    main()
