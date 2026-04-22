"""S3 cache factory extracted from src/files/s3.py.

Provides a small, import-safe factory so other S3 modules can import the
cache without importing the large `src.files.s3` module and risking
circular imports.
"""

from diskcache import Cache


def _s3_cache() -> Cache:
    """Get the RSS feed cache instance."""
    return Cache(".cache/s3")


__all__ = ["_s3_cache"]
