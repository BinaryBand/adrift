from typing import Literal

from pydantic import BaseModel

from src.models.metadata import RssEpisode
from src.models.output import EpisodeData
from src.models.podcast_config import PodcastConfig, SourceFilter


class SourceTrace(BaseModel):
    """Per-source pipeline trace used for diagnostics and visualization."""

    role: Literal["reference", "download"]
    url: str
    source_type: Literal["rss", "youtube"]
    episode_count: int
    filters: SourceFilter
    has_filters: bool


class MatchCandidateTrace(BaseModel):
    """Scored candidate considered for a reference episode during alignment."""

    download_index: int
    score: float
    reason: Literal[
        "matched",
        "below_threshold",
        "download_matched_elsewhere",
        "reference_matched_elsewhere",
        "not_selected",
    ]


class ReferenceMatchTrace(BaseModel):
    """Compact alignment trace for one reference episode."""

    reference_index: int
    matched_download_index: int | None = None
    matched_score: float | None = None
    candidates: list[MatchCandidateTrace] = []


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
    match_traces: list[ReferenceMatchTrace] = []
    pairs: list[tuple[int, int]]
    episodes: list[EpisodeData]
    download_episodes: list[DownloadEpisode] = []
