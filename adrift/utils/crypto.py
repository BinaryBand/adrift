# cspell: words nokey noprint

import hashlib


def sha256(data: str) -> str:
    """Generate SHA-256 hash of the input data."""
    hash_obj = hashlib.sha256(data.encode("utf-8"))
    return hash_obj.hexdigest()
