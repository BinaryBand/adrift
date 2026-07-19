"""Composition root -- wires concrete adapters into the injectable AppContext.

This is the one place (in the cli layer) that constructs adapters and assembles
the AppContext. Core use-cases depend only on ports; keeping composition here
preserves the cli > adapters > core layering.
"""

from __future__ import annotations

from adrift.adapters import (
    get_alignment_backend_provider,
    get_episode_source_factory,
    get_secret_provider_adapter,
    get_storage_adapter,
    get_video_downloader,
)
from adrift.core.ports import DiskCacheAdapter
from adrift.core.services.context import AppContext, EventBus


def build_app_context() -> AppContext:
    """Construct the production AppContext from environment and defaults."""
    return AppContext(
        storage=get_storage_adapter(),
        secrets=get_secret_provider_adapter(),
        rss_cache=DiskCacheAdapter(".cache/rss"),
        yt_cache=DiskCacheAdapter(".cache/youtube"),
        event_bus=EventBus(),
        episode_source_factory=get_episode_source_factory(),
        alignment_provider=get_alignment_backend_provider(),
        video_downloader=get_video_downloader(),
    )
