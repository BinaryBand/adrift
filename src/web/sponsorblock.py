"""
SponsorBlock API integration for fetching and removing sponsored segments.
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from pathlib import Path

import requests
import sys

sys.path.insert(0, Path(__file__).parent.parent.as_posix())
from src.files.audio import cut_segments
from src.utils.cache import S3Cache
from src.utils.crypto import sha256
from src.utils.progress import Callback


# Constants
_CACHE = S3Cache(".cache/sponsorblock", "sponsorblock/segments")
_CACHE_EXPIRY_DAYS = {False: 7, True: 35}  # Days to cache (no segments vs has segments)
_API_TIMEOUT = 10

# Type aliases
ActionType = Literal["skip", "mute", "blackout"]
Category = Literal[
    "sponsor", "selfpromo", "interaction", "intro", "outro", "preview", "hook", "filler"
]


class SponsorSegment(BaseModel):
    """https://wiki.sponsor.ajay.app/w/API_Docs#GET_/api/skipSegments"""

    segment: tuple[float, float]
    uuid: str = Field(alias="UUID")
    category: Category
    video_duration: float = Field(alias="videoDuration")
    action_type: ActionType = Field(alias="actionType")
    locked: int
    votes: int
    description: str = ""

    model_config = ConfigDict(populate_by_name=True)


def _fetch_sponsor_segments(video_id: str) -> list[SponsorSegment]:
    """Fetch sponsor segments with multi-layer caching."""
    cache_key = video_id

    if (cached := _CACHE.get(cache_key)) is not None:
        return cached if isinstance(cached, list) else []

    try:
        # Use sha256 hash for API request as required by SponsorBlock
        hash_prefix = sha256(video_id)[:24]
        url = f"https://sponsor.ajay.app/api/skipSegments/{hash_prefix}"
        response = requests.get(url, timeout=_API_TIMEOUT)

        if response.status_code == 404:
            raw_data = []
        elif response.status_code == 200:
            raw_data = response.json()
            if not isinstance(raw_data, list):
                print(f"WARNING: Unexpected API response for {video_id}: not a list")
                return []

            # Handle wrapped format: [{"videoID": "...", "segments": [...]}]
            if raw_data and isinstance(raw_data[0], dict) and "segments" in raw_data[0]:
                raw_data = raw_data[0]["segments"]
        else:
            response.raise_for_status()
            return []

        segments = [SponsorSegment.model_validate(item) for item in raw_data]

        expire_days = _CACHE_EXPIRY_DAYS[len(segments) > 0]
        _CACHE.set(cache_key, segments, expire=expire_days * 24 * 3600)

        return segments

    except requests.RequestException as e:
        print(f"WARNING: Network error fetching segments for {video_id}: {e}")
    except Exception as e:
        print(f"WARNING: Error fetching segments for {video_id}: {e}")

    return []


def fetch_sponsor_segments(video_id: str) -> list[tuple[float, float]]:
    """Fetch sponsor segments as list of (start, end) time tuples."""
    try:
        segments = _fetch_sponsor_segments(video_id)
        return [seg.segment for seg in segments]
    except Exception as e:
        print(f"ERROR: Error fetching segments for {video_id}: {e}")
        return []


def remove_sponsors(
    target: Path, video_id: str, callback: Callback | None = None
) -> bool:
    """Remove sponsor segments from an audio file."""
    segments = fetch_sponsor_segments(video_id)
    if not segments:
        return False
    elif callback:
        callback(0, len(segments))

    try:
        print(f"Removing {len(segments)} sponsor segments from {target}")
        cut_segments(target, segments, callback=callback)
        return True
    except Exception as e:
        print(f"ERROR: Error removing sponsors from {target}: {e}")
        return False
