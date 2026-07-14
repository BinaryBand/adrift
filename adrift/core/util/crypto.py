"""Hashing helpers (SHA-256 over strings and files)."""

# cspell: words nokey noprint

import hashlib
from pathlib import Path


def sha256(data: str) -> str:
    """Generate SHA-256 hash of the input data."""
    hash_obj = hashlib.sha256(data.encode("utf-8"))
    return hash_obj.hexdigest()


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Generate SHA-256 hash of a file's contents, streamed in chunks."""
    hash_obj = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()
