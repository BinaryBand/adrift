# ruff: noqa: E402
import sys
from pathlib import Path

import dotenv

sys.path.insert(0, Path(dotenv.find_dotenv()).parent.as_posix())
dotenv.load_dotenv()

import argparse
import tempfile
from urllib.parse import urljoin

from PIL import Image
from tqdm import tqdm

from runbook.database._convert_common import collect_podcast_targets, format_bytes

# Dedupe helpers
from src.files.images import make_square_image_to
from src.files.s3 import (
    S3_ENDPOINT,
    copy_file,
    delete_file,
    download_file,
    exists,
    get_file_list,
    get_metadata,
    set_metadata,
    upload_file,
)
from src.utils.crypto import get_file_hash
from src.utils.image_dedupe_index import (
    HashDedupeEntry,
    find_similar_by_phash,
    get_hash_dedupe,
    remember_episode_dedupe,
    remember_hash_dedupe,
)
from src.utils.image_phash import average_hash

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

_THUMB_HASH_BASE = Path("podcasts/_thumbs/by-hash")


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

            # Download source
            download_file(bucket, old_key, input_path)

            # Create a normalized WEBP for dedupe (square, same pipeline as uploads)
            normalized_file = tmpdir_path / f"{Path(filename).stem}.norm.webp"
            normalized_ok = False
            try:
                normalized_ok = make_square_image_to(
                    input_path, normalized_file, output_format="WEBP", quality=80
                )
            except Exception:
                normalized_ok = False

            file_hash = None
            phash = None
            if normalized_ok and normalized_file.exists():
                try:
                    file_hash = get_file_hash(normalized_file)
                except Exception:
                    file_hash = None
                try:
                    phash = average_hash(normalized_file)
                except Exception:
                    phash = None

            # If we have a normalized hash, check for existing canonical or perceptual matches
            canonical_url: str | None = None
            if file_hash:
                canonical_stem = (_THUMB_HASH_BASE / file_hash).as_posix()
                existing_canonical = exists(bucket, canonical_stem)
                if existing_canonical:
                    canonical_path = (
                        Path(bucket) / _THUMB_HASH_BASE / existing_canonical
                    ).as_posix()
                    canonical_url = urljoin(S3_ENDPOINT, canonical_path)
                    # Record episode->hash mapping (use filename stem as episode id)
                    try:
                        author_slug = Path(prefix).name
                        episode_id = Path(filename).with_suffix("").as_posix()
                        remember_episode_dedupe(author_slug, episode_id, file_hash, canonical_url)
                    except Exception:
                        pass
                else:
                    # Try perceptual match
                    try:
                        similar = None
                        if phash:
                            similar = find_similar_by_phash(phash)
                        if similar is not None:
                            # Attempt to copy the existing canonical blob to the canonical key
                            canonical_key = f"{canonical_stem}.webp"
                            try:
                                uploaded = copy_file(bucket, similar.canonical_key, canonical_key)
                                if uploaded is not None:
                                    canonical_url = uploaded
                                    print(
                                        "Copied canonical from"
                                        f" {similar.canonical_key} to {canonical_key} ->"
                                        f" {uploaded}"
                                    )
                                    try:
                                        entry = HashDedupeEntry(
                                            file_hash=file_hash,
                                            canonical_key=canonical_key,
                                            canonical_url=uploaded,
                                            output_ext=similar.output_ext,
                                            source_bytes=input_path.stat().st_size,
                                            encoded_bytes=normalized_file.stat().st_size,
                                            phash=phash,
                                        )
                                        if get_hash_dedupe(file_hash) is None:
                                            remember_hash_dedupe(entry)
                                    except Exception:
                                        pass
                                    try:
                                        author_slug = Path(prefix).name
                                        episode_id = Path(filename).with_suffix("").as_posix()
                                        remember_episode_dedupe(
                                            author_slug, episode_id, file_hash, uploaded
                                        )
                                    except Exception:
                                        pass
                                else:
                                    # fallback: map to the similar file if copy failed
                                    canonical_url = similar.canonical_url
                                    print(
                                        "Copy failed for"
                                        f" {filename}: mapping to existing canonical"
                                        f" {similar.canonical_key}"
                                    )
                                    try:
                                        author_slug = Path(prefix).name
                                        episode_id = Path(filename).with_suffix("").as_posix()
                                        remember_episode_dedupe(
                                            author_slug,
                                            episode_id,
                                            similar.file_hash,
                                            similar.canonical_url,
                                        )
                                    except Exception:
                                        pass
                            except Exception:
                                # on any copy error fallback to mapping to existing canonical
                                canonical_url = similar.canonical_url
                                try:
                                    author_slug = Path(prefix).name
                                    episode_id = Path(filename).with_suffix("").as_posix()
                                    remember_episode_dedupe(
                                        author_slug,
                                        episode_id,
                                        similar.file_hash,
                                        similar.canonical_url,
                                    )
                                except Exception:
                                    pass
                    except Exception:
                        similar = None

                # If no canonical found via exact or perceptual match,
                # register this normalized file as canonical
                if canonical_url is None and file_hash:
                    try:
                        canonical_key = f"{canonical_stem}.webp"
                        uploaded = upload_file(bucket, canonical_key, normalized_file)
                        if uploaded is not None:
                            print(f"Uploaded canonical {canonical_key} -> {uploaded}")
                            # Remember hash entry
                            try:
                                entry = HashDedupeEntry(
                                    file_hash=file_hash,
                                    canonical_key=canonical_key,
                                    canonical_url=uploaded,
                                    output_ext=".webp",
                                    source_bytes=input_path.stat().st_size,
                                    encoded_bytes=normalized_file.stat().st_size,
                                    phash=phash,
                                )
                                if get_hash_dedupe(file_hash) is None:
                                    remember_hash_dedupe(entry)
                            except Exception:
                                pass
                            try:
                                author_slug = Path(prefix).name
                                episode_id = Path(filename).with_suffix("").as_posix()
                                remember_episode_dedupe(
                                    author_slug, episode_id, file_hash, uploaded
                                )
                            except Exception:
                                pass
                    except Exception:
                        # If upload failed, continue with per-file conversion
                        canonical_url = None

            # Perform the per-file conversion (preserve current behavior)
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
