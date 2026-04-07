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

from runbook.database.convert_common import collect_podcast_targets, format_bytes
from src.files.s3 import (
    delete_file,
    download_file,
    get_file_list,
    get_metadata,
    set_metadata,
    upload_file,
)

_FFMPEG_BASE = ["ffmpeg", "-hide_banner", "-loglevel", "error"]


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
            input_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Download original
            download_file(bucket, old_key, input_path)

            # Transcode to opus
            _convert_to_opus(input_path, output_path)

            old_size = input_path.stat().st_size
            new_size = output_path.stat().st_size
            saved_size = max(0, old_size - new_size)
            saved_pct = (saved_size / old_size * 100) if old_size > 0 else 0.0

            # Upload new .opus file
            upload_file(bucket, new_key, output_path)

            # Copy metadata to new key
            metadata = get_metadata(bucket, old_key)
            if metadata is not None:
                set_metadata(bucket, new_key, metadata)

            # Delete original .m4a
            delete_file(bucket, old_key)

            print(
                f"Saved for {filename}: "
                f"{format_bytes(old_size)} -> {format_bytes(new_size)} "
                f"(-{format_bytes(saved_size)}, {saved_pct:.1f}%)"
            )

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
        description="Convert .m4a files to Opus for all podcasts discovered from config/*.toml."
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
    """Main orchestration: list files, convert each across all podcast paths."""
    args = _parse_args()
    targets = collect_podcast_targets()
    if not targets:
        print("No podcast targets found under config/*.toml")
        return

    total_successes, total_errors, total_already_opus = 0, 0, 0
    remaining = args.limit

    for bucket, prefix in targets:
        if remaining is not None and remaining <= 0:
            break

        filenames = get_file_list(bucket, prefix)
        to_convert = [f for f in filenames if f.lower().endswith(".m4a")]
        opus_count = sum(1 for f in filenames if f.lower().endswith(".opus"))
        total_already_opus += opus_count

        if remaining is not None:
            to_convert = to_convert[:remaining]

        if not to_convert:
            continue

        print(f"\nProcessing {bucket}/{prefix}: {len(to_convert)} .m4a files")
        for filename in tqdm(to_convert, desc=f"Converting {prefix}"):
            ok = _convert_key(bucket, prefix, filename, dry_run=args.dry_run)
            if ok:
                total_successes += 1
            else:
                total_errors += 1

            if remaining is not None:
                remaining -= 1
                if remaining <= 0:
                    break

    print(
        f"\nDone. Converted: {total_successes}, "
        f"Errors: {total_errors}, Already .opus: {total_already_opus}"
    )


if __name__ == "__main__":
    main()
