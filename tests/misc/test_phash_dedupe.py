import sys
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())

from src.utils.image_dedupe_index import HashDedupeEntry, find_similar_by_phash
from src.utils.image_phash import average_hash, hamming_distance


def test_average_hash_identical(tmp_path: Path) -> None:
    p1: Path = tmp_path / "img1.png"
    p2: Path = tmp_path / "img2.png"
    Image.new("RGB", (8, 8), (255, 255, 255)).save(p1)
    Image.new("RGB", (8, 8), (255, 255, 255)).save(p2)

    h1 = average_hash(p1)
    h2 = average_hash(p2)
    assert h1 == h2
    assert hamming_distance(h1, h2) == 0


def test_average_hash_small_change(tmp_path: Path) -> None:
    p1: Path = tmp_path / "img1.png"
    p2: Path = tmp_path / "img2.png"
    img = Image.new("RGB", (8, 8), (255, 255, 255))
    img.save(p1)
    img2 = img.copy()
    img2.putpixel((0, 0), (0, 0, 0))
    img2.save(p2)

    h1 = average_hash(p1)
    h2 = average_hash(p2)
    dist = hamming_distance(h1, h2)
    assert dist > 0


def test_find_similar_by_phash_hit(tmp_path: Path) -> None:
    # Create two similar images and compute their phashes
    p1 = tmp_path / "base.png"
    p2 = tmp_path / "near.png"
    Image.new("RGB", (8, 8), (255, 255, 255)).save(p1)
    img2 = Image.new("RGB", (8, 8), (255, 255, 255))
    img2.putpixel((1, 1), (0, 0, 0))
    img2.save(p2)

    ph1 = average_hash(p1)

    # Use exact phash match to validate lookup behavior
    entry = HashDedupeEntry(
        file_hash="deadbeef",
        canonical_key="podcasts/_thumbs/by-hash/deadbeef.webp",
        canonical_url="https://example.com/media/deadbeef.webp",
        output_ext=".webp",
        source_bytes=1234,
        encoded_bytes=432,
        phash=ph1,
    )

    with patch("src.utils.image_dedupe_index._list_hash_entries", return_value=[entry]):
        found = find_similar_by_phash(ph1, max_distance=6)

    assert found is not None
    assert found.canonical_url == entry.canonical_url


def test_find_similar_by_phash_no_match() -> None:
    entry = HashDedupeEntry(
        file_hash="deadbeef",
        canonical_key="podcasts/_thumbs/by-hash/deadbeef.webp",
        canonical_url="https://example.com/media/deadbeef.webp",
        output_ext=".webp",
        source_bytes=1234,
        encoded_bytes=432,
        phash="0" * 16,
    )

    with patch("src.utils.image_dedupe_index._list_hash_entries", return_value=[entry]):
        found = find_similar_by_phash("f" * 16, max_distance=2)

    assert found is None
