"""Enrichment helpers for the download pipeline."""

from src.models import DownloadEpisode, MergeResult
from src.utils.regex import YOUTUBE_VIDEO_REGEX
from src.web.sponsorblock import fetch_sponsor_segments


def _extract_video_id(content: str) -> str | None:
    m = YOUTUBE_VIDEO_REGEX.search(content)
    return m.group(4) if m else None


def enrich_with_sponsors(result: MergeResult) -> list[DownloadEpisode]:
    """Pair each download-side episode with its sponsor segments."""
    episodes: list[DownloadEpisode] = []
    for _ref_idx, dl_idx in result.pairs:
        ep = result.downloads[dl_idx]
        video_id = _extract_video_id(ep.content)
        segments = fetch_sponsor_segments(video_id) if video_id else []
        episodes.append(DownloadEpisode(episode=ep, sponsor_segments=segments, video_id=video_id))
    result.download_episodes = episodes
    return episodes


__all__ = ["enrich_with_sponsors", "_extract_video_id"]
