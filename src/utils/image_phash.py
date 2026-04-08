from pathlib import Path
from typing import Any, cast

from PIL import Image


def average_hash(file: Path, hash_size: int = 8) -> str:
    """Compute an average (aHash) perceptual hash for an image file.

    Returns a hex string representation of the hash.
    """
    with Image.open(file) as img:
        img = img.convert("L")
        # Resize to a small square and compute a simple average hash
        img = img.resize((hash_size, hash_size), Image.Resampling.LANCZOS)
        pixels = cast(list[int], list(cast(Any, img).getdata()))
        avg = sum(pixels) / len(pixels)
        bits = 0
        for p in pixels:
            bits = (bits << 1) | (1 if p > avg else 0)

    hex_len = (hash_size * hash_size + 3) // 4
    return f"{bits:0{hex_len}x}"


def hamming_distance(hex1: str, hex2: str) -> int:
    """Return the Hamming distance between two hex-represented bitstrings.

    Pads the shorter hex string with leading zeros before comparison.
    """
    max_len = max(len(hex1), len(hex2))
    a = int(hex1.rjust(max_len, "0"), 16)
    b = int(hex2.rjust(max_len, "0"), 16)
    return (a ^ b).bit_count()
