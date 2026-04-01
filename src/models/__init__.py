"""Package wrapper for model definitions.

This module re-exports names from the legacy `metadata` module so that both
`src.models` and `src.models.metadata` imports work. It preserves the
`DEVICE`/`PROJECT` constants and public model classes.
"""

from .metadata import (
    DEVICE,
    PROJECT,
    CacheMetadata,
    MediaMetadata,
    RssChannel,
    RssEpisode,
    S3Metadata,
    YtDlpParams,
)
from .output import EpisodeData, PodcastFeed

__all__ = [
    "DEVICE",
    "PROJECT",
    "S3Metadata",
    "CacheMetadata",
    "MediaMetadata",
    "YtDlpParams",
    "RssChannel",
    "RssEpisode",
    "EpisodeData",
    "PodcastFeed",
]
