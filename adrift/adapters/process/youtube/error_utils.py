from __future__ import annotations

from collections.abc import Callable

ReasonMatcher = Callable[[str, str], bool]


def _contains_age_gate(error_text: str, _: str) -> bool:
    return "Sign in to confirm your age" in error_text


def _contains_premiere(error_text: str, _: str) -> bool:
    return "Premieres in " in error_text


def _contains_live_not_started(error_text: str, _: str) -> bool:
    return "This live event will begin in" in error_text


def _contains_private(error_text: str, error_lower: str) -> bool:
    return "private video" in error_lower or "This video is private" in error_text


def _contains_members_only(error_text: str, error_lower: str) -> bool:
    return "members-only" in error_lower or "channel members" in error_lower


def _contains_geo_restriction(_: str, error_lower: str) -> bool:
    return (
        "not available in your country" in error_lower
        or "available in your country" in error_lower
        or ("geo" in error_lower and "block" in error_lower)
    )


def _contains_removed(error_text: str, _: str) -> bool:
    return (
        "This video has been removed" in error_text
        or "This video is no longer available" in error_text
    )


def _contains_unavailable(error_text: str, _: str) -> bool:
    return "Video unavailable" in error_text


_REASON_RULES: tuple[tuple[ReasonMatcher, str], ...] = (
    (_contains_age_gate, "age-restricted; retrying with authentication"),
    (_contains_premiere, "premiere not yet available"),
    (_contains_live_not_started, "live event not yet started"),
    (_contains_private, "private video"),
    (_contains_members_only, "members-only video"),
    (_contains_geo_restriction, "geo-restricted video"),
    (_contains_removed, "removed video"),
    (_contains_unavailable, "video unavailable"),
)


def yt_dlp_retry_reason(error: Exception, unavailable_message: str) -> str:
    error_text = str(error)
    error_lower = error_text.lower()
    for matcher, reason in _REASON_RULES:
        if matcher(error_text, error_lower):
            return reason
    if "Requested format is not available" in error_text:
        return unavailable_message
    if "This video is only available for" in error_text:
        return "restricted format set; trying fallback"
    first_line = error_text.splitlines()[0].strip()
    return first_line[:160]
