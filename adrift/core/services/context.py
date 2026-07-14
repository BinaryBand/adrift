"""Application context — single injectable root for all services.

AppContext carries every injectable service needed by use-cases, adapters,
and pipelines. This replaces module-level globals like _default_s3_service.

Every operation that needs I/O receives AppContext as a parameter.
Testing is trivial: construct an AppContext with mock ports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from adrift.core.ports import (
        AlignmentBackendProviderPort,
        CachePort,
        EpisodeSourceFactoryPort,
        SecretProviderPort,
        StoragePort,
        VideoDownloaderPort,
    )


@dataclass
class EventBus:
    """Simple event publishing system for pipeline events.

    Replaces the wired callback pattern (DownloadProgressHooks).
    Code publishes typed events; subscribers (UI, tests, metrics) listen.
    """

    # Map from event type to list of handlers
    _subscribers: dict[type, list[Callable[[Any], None]]] = field(default_factory=dict)

    def publish(self, event: object) -> None:
        """Publish an event to all subscribers of its type."""
        event_type = type(event)
        handlers = self._subscribers.get(event_type, [])
        for handler in handlers:
            handler(event)

    def subscribe(self, event_type: type, handler: Callable[[Any], None]) -> None:
        """Subscribe a handler to events of a specific type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)


@dataclass(frozen=True)
class AppContext:
    """Single injectable root for all application services.

    Every use-case, adapter, and pipeline stage receives this as context.
    No implicit module state; all dependencies are explicit and testable.

    Attributes:
        storage: StoragePort for object storage operations (upload, list, delete)
        secrets: SecretProviderPort for credentials
        rss_cache: CachePort for RSS feed caching
        yt_cache: CachePort for YouTube metadata caching
        event_bus: EventBus for publishing pipeline events
        episode_source_factory: resolves episode-source adapters per FeedSource
        alignment_provider: provides the scored-alignment backend
        video_downloader: downloads video URLs to local audio files

    The three factory/provider ports are injected by the cli composition root
    (see adrift.cli.composition); they default to None so tests that do not
    exercise those paths can construct AppContext without wiring them.
    """

    storage: StoragePort
    secrets: SecretProviderPort
    rss_cache: CachePort[Any]
    yt_cache: CachePort[Any]
    event_bus: EventBus
    episode_source_factory: EpisodeSourceFactoryPort | None = None
    alignment_provider: AlignmentBackendProviderPort | None = None
    video_downloader: VideoDownloaderPort | None = None


__all__ = [
    "AppContext",
    "EventBus",
]
