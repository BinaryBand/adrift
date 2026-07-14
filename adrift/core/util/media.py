"""Shared media utilities used across web and file-handling layers."""

import logging

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".mp4", ".opus"}

_DURATION_WEIGHTS: dict[int, tuple[int, ...]] = {
    1: (1,),
    2: (60, 1),
    3: (3600, 60, 1),
}


def parse_duration(duration_str: str | None) -> float | None:
    """Parse a duration string in HH:MM:SS or MM:SS format to total seconds."""
    if not duration_str:
        return None
    parts = duration_str.split(":")
    weights = _DURATION_WEIGHTS.get(len(parts))
    if weights is None:
        logger.warning("Unrecognized duration format: %s", duration_str)
        return None
    return sum(w * float(p) for w, p in zip(weights, parts))
