# noqa: F841,F821
from __future__ import annotations

from typing import Generic, Protocol, TypeVar

T = TypeVar("T")


class CachePort(Protocol[T]):
    """Protocol for caching operations.

    Implementations provide get, set, and delete with optional TTL.
    This abstraction allows swapping diskcache for in-memory or Redis
    without changing callers (e.g., RSS fetcher, YouTube metadata fetcher).
    """

    def get(self, key: str, default: T | None = None) -> T | None:  # noqa: F841
        """Get a value from the cache.

        Args:
            key: Cache key
            default: Default value if key not found

        Returns:
            The cached value, or default if not found
        """
        ...

    def set(self, key: str, value: T, ttl: int | None = None) -> None:  # noqa: F841
        """Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache (must be serializable)
            ttl: Optional time-to-live in seconds

        Raises:
            CacheError if set fails
        """
        ...

    def delete(self, key: str) -> None:  # noqa: F841
        """Delete a value from the cache.

        Args:
            key: Cache key

        Raises:
            CacheError if delete fails
        """
        ...


class DiskCacheAdapter(Generic[T]):
    """Adapter wrapping diskcache.Cache for CachePort protocol.

    Production implementation using persistent disk-based caching.
    """

    def __init__(self, cache_dir: str) -> None:
        """Initialize disk cache adapter.

        Args:
            cache_dir: Directory path for cache storage
        """
        import diskcache

        self._cache: diskcache.Cache = diskcache.Cache(cache_dir)

    def get(self, key: str, default: T | None = None) -> T | None:
        """Get value from disk cache."""
        return self._cache.get(key, default)

    def set(self, key: str, value: T, ttl: int | None = None) -> None:  # noqa: F841
        """Set value in disk cache with optional TTL."""
        self._cache[key] = value

    def delete(self, key: str) -> None:
        """Delete value from disk cache."""
        del self._cache[key]


class InMemoryCache(Generic[T]):
    """In-memory cache implementation for testing.

    Fast but ephemeral; useful for unit tests and development.
    """

    def __init__(self) -> None:
        """Initialize empty in-memory cache."""
        self._store: dict[str, T] = {}

    def get(self, key: str, default: T | None = None) -> T | None:
        """Get value from memory."""
        return self._store.get(key, default)

    def set(self, key: str, value: T, ttl: int | None = None) -> None:  # noqa: F841
        """Set value in memory (ignores ttl)."""
        self._store[key] = value

    def delete(self, key: str) -> None:
        """Delete value from memory."""
        if key in self._store:
            del self._store[key]


__all__ = [
    "CachePort",
    "DiskCacheAdapter",
    "InMemoryCache",
]
