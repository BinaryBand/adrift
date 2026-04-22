"""
SponsorBlock API integration for fetching and removing sponsored segments.
"""

import logging
from pathlib import Path
from typing import Any, cast

import requests

from src.files.audio import cut_segments
from src.models import SponsorSegment
from src.utils.cache import S3Cache
from src.utils.crypto import sha256
from src.utils.progress import Callback

logger = logging.getLogger(__name__)

# Constants
_CACHE = S3Cache(".cache/sponsorblock", "sponsorblock/segments")
_CACHE_EXPIRY_DAYS = {False: 7, True: 35}  # Days to cache (no segments vs has segments)
_API_TIMEOUT = 10


def _fetch_sponsor_segments(video_id: str) -> list[SponsorSegment]:
    """Fetch sponsor segments with multi-layer caching."""
    cached = _cached_segments(video_id)
    if cached is not None:
        return cached

    try:
        raw_segments = _fetch_segment_payload(video_id)
        segments = _validate_segments(raw_segments)
        _cache_segments(video_id, segments)
        return segments
    except requests.RequestException as e:
        logger.warning("Network error fetching segments for %s: %s", video_id, e)
    except Exception as e:
        logger.warning("Error fetching segments for %s: %s", video_id, e)

    return []


def _cached_segments(video_id: str) -> list[SponsorSegment] | None:
    cached = _CACHE.get(video_id)
    if cached is None:
        return None
    return cast(list[SponsorSegment], cached) if isinstance(cached, list) else []


def _fetch_segment_payload(video_id: str) -> list[dict[str, Any]]:
    response = requests.get(_segment_api_url(video_id), timeout=_API_TIMEOUT)
    return _parse_segment_payload(video_id, response)


def _segment_api_url(video_id: str) -> str:
    hash_prefix = sha256(video_id)[:24]
    return f"https://sponsor.ajay.app/api/skipSegments/{hash_prefix}"


def _parse_segment_payload(video_id: str, response: requests.Response) -> list[dict[str, Any]]:
    if response.status_code == 404:
        return []
    if response.status_code != 200:
        response.raise_for_status()
        return []

    raw_data = response.json()
    if not isinstance(raw_data, list):
        logger.warning("Unexpected API response for %s: not a list", video_id)
        return []
    return _unwrap_segment_payload(cast(list[dict[str, Any]], raw_data))


def _unwrap_segment_payload(raw_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if raw_data and "segments" in raw_data[0]:
        nested = raw_data[0].get("segments", [])
        return cast(list[dict[str, Any]], nested) if isinstance(nested, list) else []
    return raw_data


def _validate_segments(raw_segments: list[dict[str, Any]]) -> list[SponsorSegment]:
    return [SponsorSegment.model_validate(item) for item in raw_segments]


def _cache_segments(video_id: str, segments: list[SponsorSegment]) -> None:
    expire_days = _CACHE_EXPIRY_DAYS[len(segments) > 0]
    _CACHE.set(video_id, segments, expire=expire_days * 24 * 3600)


def fetch_sponsor_segments(video_id: str) -> list[tuple[float, float]]:
    """Fetch sponsor segments as list of (start, end) time tuples."""
    try:
        segments = _fetch_sponsor_segments(video_id)
        return [seg.segment for seg in segments]
    except Exception as e:
        logger.error("Error fetching segments for %s: %s", video_id, e)
        return []


def remove_sponsors(target: Path, video_id: str, callback: Callback | None = None) -> bool:
    """Remove sponsor segments from an audio file."""
    segments = fetch_sponsor_segments(video_id)
    if not segments:
        return False
    elif callback:
        callback(0, len(segments))

    try:
        logger.info("Removing %d sponsor segments from %s", len(segments), target)
        cut_segments(target, segments, callback=callback)
        return True
    except Exception as e:
        logger.error("Error removing sponsors from %s: %s", target, e)
        return False
