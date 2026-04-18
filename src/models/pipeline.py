from typing import Literal

from pydantic import BaseModel

from src.app_common import PodcastConfig, SourceFilter
from src.models.metadata import RssEpisode
from src.models.output import EpisodeData


class SourceTrace(BaseModel):
    """Per-source pipeline trace used for diagnostics and visualization."""

    role: Literal["reference", "download"]
    url: str
    source_type: Literal["rss", "youtube"]
    episode_count: int
    filters: SourceFilter
    has_filters: bool


class DownloadEpisode(BaseModel):
    """A download-side episode paired with its pre-fetched sponsor segment data."""

    episode: RssEpisode
    sponsor_segments: list[tuple[float, float]] = []
    video_id: str | None = None


class MergeResult(BaseModel):
    """Complete pipeline trace for one podcast series.

    Captures every stage of the resolution path:
      config → (references, downloads) → pairs → episodes

    `download_episodes` is empty until the download pipeline enriches it with
    sponsor segments fetched per-episode.
    """

    config: PodcastConfig
    references: list[RssEpisode]
    downloads: list[RssEpisode]
    source_traces: list[SourceTrace] = []
    pairs: list[tuple[int, int]]
    episodes: list[EpisodeData]
    download_episodes: list[DownloadEpisode] = []
