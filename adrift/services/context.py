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
    from adrift.adapters.ports.cache import CachePort
    from adrift.adapters.ports.secrets import SecretProviderPort
    from adrift.adapters.ports.storage import StoragePort


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
        s3: StoragePort for S3 operations (upload, download, list)
        secrets: SecretProviderPort for credentials
        rss_cache: CachePort for RSS feed caching
        yt_cache: CachePort for YouTube metadata caching
        event_bus: EventBus for publishing pipeline events
    """

    s3: StoragePort
    secrets: SecretProviderPort
    rss_cache: CachePort
    yt_cache: CachePort
    event_bus: EventBus

    @classmethod
    def from_env(cls) -> AppContext:
        """Construct AppContext from environment and defaults.

        This is the production factory method. It initializes all adapters
        from environment variables, secrets, and configuration files.

        For testing, construct AppContext directly with mock ports.
        """
        # Import here to avoid circular imports

        from adrift.adapters import get_secret_provider_adapter
        from adrift.adapters.ports.cache import DiskCacheAdapter
        from adrift.services.files.s3 import S3Service

        secrets = get_secret_provider_adapter()
        return cls(
            s3=S3Service(secrets),  # type: ignore  # S3Service implements StoragePort (Phase B)
            secrets=secrets,
            rss_cache=DiskCacheAdapter(".cache/rss"),
            yt_cache=DiskCacheAdapter(".cache/youtube"),
            event_bus=EventBus(),
        )


__all__ = [
    "AppContext",
    "EventBus",
]
