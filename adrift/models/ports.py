from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Protocol, TypeVar, runtime_checkable

from adrift.models import AlignmentConfig, FeedSource, RssChannel, RssEpisode

Callback = Callable[[int, int | None], None]

T = TypeVar("T")


@dataclass(frozen=True)
class EpisodeSourceFetchContext:
    title: str = ""
    detailed: bool = True
    callback: Callback | None = None
    refresh: bool = False


@runtime_checkable
class AlignmentPort(Protocol):
    def align_episodes(
        self,
        references: list[RssEpisode],
        downloads: list[RssEpisode],
        alignment: AlignmentConfig | None = None,
    ) -> list[tuple[int, int]]: ...


@runtime_checkable
class ScoredAlignmentPort(Protocol):
    def align_with_scores(
        self,
        references: list[RssEpisode],
        downloads: list[RssEpisode],
        **kwargs: object,
    ) -> tuple[list[tuple[int, int]], dict[tuple[int, int], float]]: ...


@runtime_checkable
class EpisodeSourcePort(Protocol):
    def fetch_episodes(
        self,
        source: FeedSource,
        context: EpisodeSourceFetchContext | None = None,
    ) -> list[RssEpisode]: ...

    def fetch_channel(self, source: FeedSource) -> RssChannel: ...


@runtime_checkable
class SecretProviderPort(Protocol):
    source_name: str

    def get(self, key: str, default: str = "") -> str: ...


@dataclass(frozen=True)
class UploadRequest:
    bucket: str
    key: str
    path: Path
    metadata: dict[str, str] | None = None


@runtime_checkable
class StoragePort(Protocol):
    def upload(self, request: UploadRequest) -> str: ...

    def download(self, bucket: str, key: str, dest: Path) -> None: ...

    def exists(self, bucket: str, prefix: str) -> bool: ...

    def list_keys(self, bucket: str, prefix: str) -> list[str]: ...


class CachePort(Protocol[T]):
    def get(self, key: str, default: T | None = None) -> T | None: ...

    def set(self, key: str, value: T, expire: int | None = None) -> None: ...

    def delete(self, key: str) -> None: ...


class DiskCacheAdapter(Generic[T]):
    def __init__(self, cache_dir: str) -> None:
        import diskcache

        self._cache: diskcache.Cache = diskcache.Cache(cache_dir)

    def get(self, key: str, default: T | None = None) -> T | None:
        return self._cache.get(key, default)

    def set(self, key: str, value: T, expire: int | None = None) -> None:
        self._cache.set(key, value, expire=expire)

    def delete(self, key: str) -> None:
        del self._cache[key]


class InMemoryCache(Generic[T]):
    def __init__(self) -> None:
        self._store: dict[str, T] = {}

    def get(self, key: str, default: T | None = None) -> T | None:
        return self._store.get(key, default)

    def set(self, key: str, value: T, expire: int | None = None) -> None:
        del expire
        self._store[key] = value

    def delete(self, key: str) -> None:
        if key in self._store:
            del self._store[key]


def require_secrets(provider: SecretProviderPort, keys: Sequence[str]) -> dict[str, str]:
    values = {key: provider.get(key, "") for key in keys}
    missing = [key for key, value in values.items() if _is_missing_or_placeholder(key, value)]
    if missing:
        raise RuntimeError(f"Missing required S3 environment variables: {', '.join(missing)}")
    return values


def _is_missing_or_placeholder(key: str, value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return True
    return stripped in {key, f"${key}", f"${{{key}}}"}
