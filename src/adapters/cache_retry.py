"""Unified cache retry/race-aware wrapper for cache operations."""

from __future__ import annotations

import time
from typing import Protocol, TypeVar

T = TypeVar("T")


class CachePort(Protocol):
    """Minimal cache interface for retry wrapper operations."""

    def get(self, key: str) -> T:
        """Get a value from cache."""
        ...

    def set(self, key: str, value: T, expire: int | None = None) -> None:
        """Set a value in cache."""
        ...

    def delete(self, key: str) -> None:
        """Delete a key from cache."""
        ...

    @property
    def directory(self) -> str:
        """Get the cache directory path."""
        ...


class RaceAwareCacheWrapper:
    """Wraps a cache instance with race-aware retry logic for concurrent access.

    Handles FileNotFoundError exceptions that occur when diskcache removes
    empty directories and concurrent writers attempt to create files in
    nested subdirectories. Retries with exponential backoff and directory
    recreation.
    """

    def __init__(self, cache: CachePort, max_attempts: int = 3, retry_delay: float = 0.05):
        """Initialize the wrapper.

        Args:
            cache: The underlying cache instance to wrap.
            max_attempts: Maximum number of retry attempts.
            retry_delay: Initial delay in seconds between retries (fixed, not exponential).
        """
        self.cache = cache
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay

    def get(self, key: str):
        """Get a value from cache with no retry (reads don't race)."""
        return self.cache.get(key)

    def set(self, key: str, value, expire: int | None = None) -> None:
        """Set a value in cache with retry on FileNotFoundError.

        Retries if parent directories are missing, recreating them as needed.
        """
        for attempt in range(self.max_attempts):
            try:
                self.cache.set(key, value, expire=expire)
                return
            except FileNotFoundError:
                self._recreate_cache_dir()
                if attempt + 1 < self.max_attempts:
                    time.sleep(self.retry_delay)
                    continue
                raise

    def delete(self, key: str) -> None:
        """Delete a key from cache with no retry."""
        return self.cache.delete(key)

    def _recreate_cache_dir(self) -> None:
        """Recreate the cache directory if it was removed by concurrent cleanup."""
        try:
            from pathlib import Path

            cache_dir = Path(self.cache.directory)
            cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # Ignore errors during directory recreation; the next retry will handle it
            pass
