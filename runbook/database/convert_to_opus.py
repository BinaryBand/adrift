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

from src.app_common import _load_config
from src.files.s3 import (
    delete_file,
    download_file,
    get_file_list,
    get_metadata,
    set_metadata,
    upload_file,
)

_FFMPEG_BASE = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
SYSK_CONFIG_FILE = "config/youtube.toml"
SYSK_FALLBACK_PATH = "/media/podcasts/stuff-you-should-know"


def _get_sysk_path() -> tuple[str, str]:
    """Load SYSK config and return (bucket, prefix)."""
    try:
        configs = _load_config(SYSK_CONFIG_FILE)
        for config in configs:
            if "stuff-you-should-know" in config.path:
                raw = Path(config.path)
                bucket = raw.parts[1]
                prefix = Path(*raw.parts[2:]).as_posix()
                return bucket, prefix
    except Exception as e:
        print(f"WARNING: Failed to load config: {e}. Using fallback path.")

    # Fallback: parse hardcoded path
    raw = Path(SYSK_FALLBACK_PATH)
    bucket = raw.parts[1]
    prefix = Path(*raw.parts[2:]).as_posix()
    return bucket, prefix


def _new_key(old_key: str) -> str:
    """Convert .m4a key to .opus."""
    return Path(old_key).with_suffix(".opus").as_posix()


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


def _convert_key(bucket: str, prefix: str, filename: str, dry_run: bool) -> bool:
    """Convert a single .m4a file to Opus.

    Returns True on success, False on any error.
    """
    old_key = f"{prefix}/{filename}"
    new_key = _new_key(old_key)

    if dry_run:
        print(f"[DRY RUN] {old_key} → {new_key}")
        return True

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            input_path = tmpdir_path / filename
            output_path = tmpdir_path / Path(filename).with_suffix(".opus").name

            # Download original
            download_file(bucket, old_key, input_path)

            # Transcode to opus
            _convert_to_opus(input_path, output_path)

            # Upload new .opus file
            upload_file(bucket, new_key, output_path)

            # Copy metadata to new key
            metadata = get_metadata(bucket, old_key)
            if metadata is not None:
                set_metadata(bucket, new_key, metadata)

            # Delete original .m4a
            delete_file(bucket, old_key)

        return True
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else "no stderr"
        print(f"ERROR: ffmpeg failed for {old_key}: exit {e.returncode}: {stderr}")
        return False
    except Exception as e:
        print(f"ERROR: Failed to convert {old_key}: {e}")
        return False


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert SYSK .m4a files in S3 to Opus format in-place."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="List files that would be converted without making any changes.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of files to convert (default: unlimited).",
    )
    return parser.parse_args()


def main() -> None:
    """Main orchestration: list files, convert each."""
    args = _parse_args()
    bucket, prefix = _get_sysk_path()

    # Get all files in the SYSK prefix
    filenames = get_file_list(bucket, prefix)

    # Separate .m4a files to convert from already-.opus files
    to_convert = [f for f in filenames if f.endswith(".m4a")]
    opus_count = sum(1 for f in filenames if f.endswith(".opus"))

    # Apply limit if specified
    if args.limit:
        to_convert = to_convert[: args.limit]

    # Convert each file
    successes, errors = 0, 0
    for filename in tqdm(to_convert, desc="Converting to Opus"):
        ok = _convert_key(bucket, prefix, filename, dry_run=args.dry_run)
        if ok:
            successes += 1
        else:
            errors += 1

    # Summary
    print(f"\nDone. Converted: {successes}, Errors: {errors}, Already .opus: {opus_count}")


if __name__ == "__main__":
    main()
