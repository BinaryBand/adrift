"""Package wrapper for model definitions."""

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
from .pipeline import DownloadEpisode, MergeResult
from .podcast_config import FeedSource, PodcastConfig, SourceFilter
from .sponsorblock import SponsorSegment

__all__ = [
    "DEVICE",
    "PROJECT",
    "S3Metadata",
    "CacheMetadata",
    "MediaMetadata",
    "YtDlpParams",
    "RssChannel",
    "RssEpisode",
    "SourceFilter",
    "FeedSource",
    "PodcastConfig",
    "EpisodeData",
    "PodcastFeed",
    "MergeResult",
    "DownloadEpisode",
    "SponsorSegment",
]
