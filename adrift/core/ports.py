"""Port interfaces (Protocols) for the hexagonal architecture.

Every cross-layer boundary -- alignment, storage, caching, secrets, episode
sources -- is declared here as a ``typing.Protocol``. Adapters implement these
and the composition root (cli) wires concrete implementations into ``core``
use-cases, so ``core`` never imports the adapters layer.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path

    from adrift.core.models import (
        AlignmentConfig,
        FeedSource,
        MediaMetadata,
        PodcastConfig,
        RssChannel,
        RssEpisode,
        S3Metadata,
    )
    from adrift.core.models.alignment_batch import AlignmentBatch
    from adrift.core.models.output import EpisodeData
    from adrift.core.models.pipeline import ReferenceMatchTrace, SourceTrace
    from adrift.core.models.storage_options import UploadOptions

AlignmentResult = tuple[list[tuple[int, int]], dict[tuple[int, int], float]]

Callback = Callable[[int, int | None], None]

T = TypeVar("T")


@dataclass(frozen=True)
class EpisodeSourceFetchContext:
    """Options controlling a single episode-source fetch."""

    title: str = ""
    detailed: bool = True
    callback: Callback | None = None
    refresh: bool = False


@runtime_checkable
class AlignmentPort(Protocol):
    """Aligns reference episodes against download episodes."""

    def align_episodes(
        self,
        references: list[RssEpisode],
        downloads: list[RssEpisode],
        alignment: AlignmentConfig | None = None,
    ) -> list[tuple[int, int]]:
        """Return matched (reference, download) index pairs."""
        ...


@runtime_checkable
class ScoredAlignmentPort(Protocol):
    """Aligns episodes and returns per-pair match scores."""

    def align_with_scores(
        self,
        references: list[RssEpisode],
        downloads: list[RssEpisode],
        **kwargs: object,
    ) -> AlignmentResult:
        """Return matched index pairs and their similarity scores."""
        ...


@runtime_checkable
class ScoredAlignmentBatchPort(Protocol):
    """Scores a pre-built alignment batch in one call."""

    def align_batch(
        self,
        batch: AlignmentBatch,
    ) -> AlignmentResult:
        """Return matched index pairs and their similarity scores."""
        ...


@runtime_checkable
class EpisodeCollectorPort(Protocol):
    """Collects episodes for a podcast config from its sources."""

    def collect(
        self,
        config: PodcastConfig,
        *,
        is_reference: bool,
        callback: Callable[[int, int | None], None] | None = None,
        refresh_sources: bool = False,
    ) -> tuple[list[RssEpisode], list[SourceTrace]]:
        """Return collected episodes and per-source traces."""
        ...


@runtime_checkable
class MatchTraceBuilderPort(Protocol):
    """Builds diagnostic traces for reference/download matches."""

    def build(
        self,
        references: list[RssEpisode],
        downloads: list[RssEpisode],
        pairs: list[tuple[int, int]],
        show: str,
        scores: dict[tuple[int, int], float],
    ) -> list[ReferenceMatchTrace]:
        """Return one trace per reference episode."""
        ...


@runtime_checkable
class EpisodeMergerPort(Protocol):
    """Merges aligned reference/download episodes into output records."""

    def merge(
        self,
        references: list[RssEpisode],
        downloads: list[RssEpisode],
        pairs: list[tuple[int, int]],
    ) -> list[EpisodeData]:
        """Return merged episode records for the emitted feed."""
        ...


@runtime_checkable
class EpisodeSourcePort(Protocol):
    """Fetches episodes and channel metadata from a single feed source."""

    def fetch_episodes(
        self,
        source: FeedSource,
        context: EpisodeSourceFetchContext | None = None,
    ) -> list[RssEpisode]:
        """Return the episodes exposed by ``source``."""
        ...

    def fetch_channel(self, source: FeedSource) -> RssChannel:
        """Return channel-level metadata for ``source``."""
        ...


@runtime_checkable
class EpisodeSourceFactoryPort(Protocol):
    """Resolves the concrete episode-source adapter for a given FeedSource.

    The composition root (cli) supplies the implementation; core use-cases
    depend only on this port so they never import the adapters layer.
    """

    def get(self, source: FeedSource) -> EpisodeSourcePort:
        """Return the episode-source adapter handling ``source``."""
        ...


@runtime_checkable
class AlignmentBackendProviderPort(Protocol):
    """Provides the scored-alignment backend (or None for the legacy path)."""

    def get(
        self, backend_name: str | None = None
    ) -> ScoredAlignmentPort | ScoredAlignmentBatchPort | None:
        """Return the selected scored-alignment backend, if any."""
        ...


@runtime_checkable
class VideoDownloaderPort(Protocol):
    """Downloads a video URL to a local audio file."""

    def download(self, url: str, dest: Path, callback: Callback | None = None) -> Path | None:
        """Download ``url`` to ``dest`` and return the written path."""
        ...


@runtime_checkable
class SecretProviderPort(Protocol):
    """Resolves named secrets from a backing store."""

    source_name: str

    def get(self, key: str, default: str = "") -> str:
        """Return the secret for ``key`` or ``default`` if unset."""
        ...


@runtime_checkable
class StoragePort(Protocol):
    """Persists and retrieves media files and their metadata."""

    def upload_file(
        self,
        bucket_key: tuple[str, str],
        file_path: Path,
        options: UploadOptions | S3Metadata | dict[str, object] | None = None,
    ) -> str | None:
        """Upload ``file_path`` to ``bucket_key`` and return its public URL."""
        ...

    def exists(self, bucket: str, prefix: str, *, extension_agnostic: bool = True) -> str | None:
        """Return the stored key matching ``prefix`` if one exists."""
        ...

    def get_file_list(
        self, bucket: str, prefix: str, *, without_extensions: bool = False
    ) -> list[str]:
        """Return stored keys under ``prefix``."""
        ...

    def get_public_urls(self, bucket: str, prefix: str) -> list[str]:
        """Return public URLs for every object under ``prefix``."""
        ...

    def get_metadata(self, bucket: str, key: str) -> MediaMetadata | None:
        """Return stored metadata for ``key`` if present."""
        ...

    def delete(self, bucket: str, key: str) -> None:
        """Delete ``key`` (and any sidecar) from ``bucket``."""
        ...


class CachePort(Protocol[T]):
    """Key-value cache for pipeline intermediate results."""

    def get(self, key: str, default: T | None = None) -> T | None:
        """Return the cached value for ``key`` or ``default``."""
        ...

    def set(self, key: str, value: T, expire: int | None = None) -> None:
        """Store ``value`` under ``key`` with an optional TTL."""
        ...

    def delete(self, key: str) -> None:
        """Remove ``key`` from the cache."""
        ...


class DiskCacheAdapter(Generic[T]):
    """Disk-backed ``CachePort`` implementation using ``diskcache``."""

    def __init__(self, cache_dir: str) -> None:
        """Open (or create) a disk cache rooted at ``cache_dir``."""
        import diskcache  # noqa: PLC0415 -- deferred so importing ports stays light

        self._cache: diskcache.Cache = diskcache.Cache(cache_dir)

    def get(self, key: str, default: T | None = None) -> T | None:
        """Return the cached value for ``key`` or ``default``."""
        return self._cache.get(key, default)

    def set(self, key: str, value: T, expire: int | None = None) -> None:
        """Store ``value`` under ``key`` with an optional TTL."""
        self._cache.set(key, value, expire=expire)

    def delete(self, key: str) -> None:
        """Remove ``key`` from the cache."""
        del self._cache[key]


class InMemoryCache(Generic[T]):
    """In-process ``CachePort`` implementation backed by a dict."""

    def __init__(self) -> None:
        """Create an empty in-memory cache."""
        self._store: dict[str, T] = {}

    def get(self, key: str, default: T | None = None) -> T | None:
        """Return the cached value for ``key`` or ``default``."""
        return self._store.get(key, default)

    def set(self, key: str, value: T, expire: int | None = None) -> None:
        """Store ``value`` under ``key`` (``expire`` is ignored)."""
        del expire
        self._store[key] = value

    def delete(self, key: str) -> None:
        """Remove ``key`` from the cache if present."""
        if key in self._store:
            del self._store[key]


def require_secrets(provider: SecretProviderPort, keys: Sequence[str]) -> dict[str, str]:
    """Return the values for ``keys``, raising if any is missing or a placeholder."""
    values = {key: provider.get(key, "") for key in keys}
    missing = [key for key, value in values.items() if _is_missing_or_placeholder(key, value)]
    if missing:
        msg = f"Missing required environment variables: {', '.join(missing)}"
        raise RuntimeError(msg)
    return values


def _is_missing_or_placeholder(key: str, value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return True
    return stripped in {key, f"${key}", f"${{{key}}}"}
