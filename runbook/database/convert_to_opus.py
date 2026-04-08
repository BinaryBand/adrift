# ruff: noqa: E402
import sys
from pathlib import Path

import dotenv

sys.path.insert(0, Path(dotenv.find_dotenv()).parent.as_posix())
dotenv.load_dotenv()

import argparse
import subprocess
import tempfile
from typing import Literal

from tqdm import tqdm

from runbook.database._convert_common import collect_podcast_targets, format_bytes
from src.files.s3 import (
    delete_file,
    download_file,
    get_file_list,
    get_metadata,
    set_metadata,
    upload_file,
)

_FFMPEG_BASE = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
DEFAULT_OPUS_BITRATE = "96k"
AUDIO_EXTENSIONS_TO_CONVERT = {
    ".m4a",
    ".mp3",
    ".aac",
    ".m4b",
    ".wav",
    ".flac",
    ".ogg",
    ".oga",
    ".wma",
    ".aif",
    ".aiff",
}


def _new_key(old_key: str) -> str:
    """Convert an audio key to .opus."""
    return Path(old_key).with_suffix(".opus").as_posix()


def _is_convertible_audio(filename: str) -> bool:
    """Return True when file extension is a supported input audio type."""
    return Path(filename).suffix.lower() in AUDIO_EXTENSIONS_TO_CONVERT


def _convert_to_opus(input_path: Path, output_path: Path, bitrate: str) -> None:
    """Convert input audio to Opus format using ffmpeg."""
    cmd = _FFMPEG_BASE + [
        "-i",
        str(input_path),
        "-c:a",
        "libopus",
        "-vbr",
        "on",
        "-compression_level",
        "10",
        "-b:a",
        bitrate,
        "-y",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _convert_key(
    bucket: str, prefix: str, filename: str, dry_run: bool, bitrate: str
) -> Literal["converted", "error"]:
    """Convert a single audio file to Opus.

    Returns conversion outcome.
    """
    old_key = f"{prefix}/{filename}"
    new_key = _new_key(old_key)

    if dry_run:
        print(f"[DRY RUN] {old_key} → {new_key}")
        return "converted"

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
            _convert_to_opus(input_path, output_path, bitrate)

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

            # Delete original source file
            delete_file(bucket, old_key)

            if new_size <= old_size:
                print(
                    f"Saved for {filename}: "
                    f"{format_bytes(old_size)} -> {format_bytes(new_size)} "
                    f"(-{format_bytes(saved_size)}, {saved_pct:.1f}%)"
                )
            else:
                expanded_size = new_size - old_size
                expanded_pct = (expanded_size / old_size * 100) if old_size > 0 else 0.0
                print(
                    f"Expanded for {filename}: "
                    f"{format_bytes(old_size)} -> {format_bytes(new_size)} "
                    f"(+{format_bytes(expanded_size)}, {expanded_pct:.1f}%)"
                )

        return "converted"
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else "no stderr"
        print(f"ERROR: ffmpeg failed for {old_key}: exit {e.returncode}: {stderr}")
        return "error"
    except Exception as e:
        print(f"ERROR: Failed to convert {old_key}: {e}")
        return "error"


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert audio files to Opus for podcasts discovered from config/*.toml."
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
    parser.add_argument(
        "--bitrate",
        type=str,
        default=DEFAULT_OPUS_BITRATE,
        metavar="RATE",
        help="Opus target bitrate (default: 96k). For speech-heavy podcasts, 64k-96k is typical.",
    )
    parser.add_argument(
        "--podcast",
        type=str,
        default=None,
        metavar="MATCH",
        help=(
            "Only convert podcasts whose prefix contains this case-insensitive "
            "substring (example: necronomipod)."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Main orchestration: list files, convert each across all podcast paths."""
    args = _parse_args()
    targets = collect_podcast_targets()
    if not targets:
        print("No podcast targets found under config/*.toml")
        return

    if args.podcast:
        needle = args.podcast.lower()
        targets = [(bucket, prefix) for bucket, prefix in targets if needle in prefix.lower()]
        if not targets:
            print(f"No podcast targets matched --podcast {args.podcast!r}")
            return

    total_successes, total_errors, total_already_opus = 0, 0, 0
    remaining = args.limit

    for bucket, prefix in targets:
        if remaining is not None and remaining <= 0:
            break

        filenames = get_file_list(bucket, prefix)
        to_convert = [f for f in filenames if _is_convertible_audio(f)]
        opus_count = sum(1 for f in filenames if f.lower().endswith(".opus"))
        total_already_opus += opus_count

        if remaining is not None:
            to_convert = to_convert[:remaining]

        if not to_convert:
            continue

        print(f"\nProcessing {bucket}/{prefix}: {len(to_convert)} audio files")
        for filename in tqdm(to_convert, desc=f"Converting {prefix}"):
            outcome = _convert_key(
                bucket, prefix, filename, dry_run=args.dry_run, bitrate=args.bitrate
            )
            if outcome == "converted":
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
