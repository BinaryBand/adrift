from pydantic import BaseModel

from src.app_common import PodcastConfig
from src.models.metadata import RssEpisode
from src.models.output import EpisodeData


class MergeResult(BaseModel):
    """Complete pipeline trace for one podcast series.

    Captures every stage of the resolution path:
      config → (references, downloads) → pairs → episodes
    """

    config: PodcastConfig
    references: list[RssEpisode]
    downloads: list[RssEpisode]
    pairs: list[tuple[int, int]]
    episodes: list[EpisodeData]
