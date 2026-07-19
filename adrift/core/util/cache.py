"""Helpers for reading from on-disk pickle caches defensively."""

import pickle
from typing import Any, Protocol


class _PickleCache(Protocol):
    def get(self, key: Any) -> Any: ...  # noqa: ANN401
    def delete(self, key: Any) -> None: ...


_UNPICKLE_ERRORS = (pickle.UnpicklingError, ModuleNotFoundError, AttributeError, EOFError)


def safe_cache_get(cache: _PickleCache, key: Any) -> Any:  # noqa: ANN401
    """Read a value from a pickle-backed cache, treating unpicklable entries as misses.

    Entries written by a since-renamed or removed module can't be unpickled;
    such entries are dropped so the caller falls back to recomputing the value.
    """
    try:
        return cache.get(key)
    except _UNPICKLE_ERRORS:
        cache.delete(key)
        return None
