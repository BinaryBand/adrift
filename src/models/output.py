from datetime import datetime
from pydantic import BaseModel


class EpisodeData(BaseModel):
    """A single podcast episode produced by the cross-alignment pipeline."""

    id: str
    title: str
    description: str
    source: list[str]  # union of all source URLs
    thumbnail: str | None = None
    upload_date: datetime | None = None


class PodcastFeed(BaseModel):
    """A fully built podcast feed ready for RSS generation."""

    id: str
    title: str
    author: str
    description: str
    source: str
    thumbnail: str | None = None
    episodes: list[EpisodeData] = []
