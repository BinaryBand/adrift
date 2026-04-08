# ruff: noqa: E402
import sys
from pathlib import Path

import dotenv

sys.path.insert(0, Path(dotenv.find_dotenv()).parent.as_posix())
dotenv.load_dotenv()

import argparse
import tempfile

from PIL import Image
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

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def _image_prefixes(prefix: str) -> list[str]:
    """Return prefixes that may contain podcast images."""
    return [prefix.rstrip("/"), f"{prefix.rstrip('/')}/thumbnails"]


def _new_key(old_key: str) -> str:
    """Convert image key suffix to .webp."""
    return Path(old_key).with_suffix(".webp").as_posix()


def _convert_image_to_webp(input_path: Path, output_path: Path, quality: int = 80) -> None:
    """Convert image to WebP format."""
    with Image.open(input_path) as img:
        if img.mode not in {"RGB", "RGBA"}:
            img = img.convert("RGB")
        img.save(output_path, format="WEBP", quality=quality, optimize=True, method=6)


def _is_convertible_image(filename: str) -> bool:
    return Path(filename).suffix.lower() in _IMAGE_EXTENSIONS


def _convert_key(bucket: str, prefix: str, filename: str, dry_run: bool) -> bool:
    """Convert a single image file to WebP.

    Returns True on success, False on any error.
    """
    old_key = f"{prefix}/{filename}"
    new_key = _new_key(old_key)

    if dry_run:
        print(f"[DRY RUN] {old_key} -> {new_key}")
        return True

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            input_path = tmpdir_path / filename
            output_path = tmpdir_path / Path(filename).with_suffix(".webp").name
            input_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            download_file(bucket, old_key, input_path)
            _convert_image_to_webp(input_path, output_path)

            old_size = input_path.stat().st_size
            new_size = output_path.stat().st_size
            saved_size = max(0, old_size - new_size)
            saved_pct = (saved_size / old_size * 100) if old_size > 0 else 0.0

            upload_file(bucket, new_key, output_path)

            metadata = get_metadata(bucket, old_key)
            if metadata is not None:
                set_metadata(bucket, new_key, metadata)

            delete_file(bucket, old_key)

            print(
                f"Saved for {filename}: "
                f"{format_bytes(old_size)} -> {format_bytes(new_size)} "
                f"(-{format_bytes(saved_size)}, {saved_pct:.1f}%)"
            )

        return True
    except Exception as e:
        print(f"ERROR: Failed to convert {old_key}: {e}")
        return False


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert image files to WebP for all podcasts discovered from config/*.toml."
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

    total_successes, total_errors, total_already_webp = 0, 0, 0
    remaining = args.limit

    for bucket, podcast_prefix in targets:
        if remaining is not None and remaining <= 0:
            break

        for prefix in _image_prefixes(podcast_prefix):
            if remaining is not None and remaining <= 0:
                break

            filenames = get_file_list(bucket, prefix)
            to_convert = [f for f in filenames if _is_convertible_image(f)]
            webp_count = sum(1 for f in filenames if f.lower().endswith(".webp"))
            total_already_webp += webp_count

            if remaining is not None:
                to_convert = to_convert[:remaining]

            if not to_convert:
                continue

            print(f"\nProcessing {bucket}/{prefix}: {len(to_convert)} images")
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
        f"Errors: {total_errors}, Already .webp: {total_already_webp}"
    )


if __name__ == "__main__":
    main()
