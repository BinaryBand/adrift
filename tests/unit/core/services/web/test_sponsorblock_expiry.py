from datetime import UTC, datetime, timedelta

from adrift.core.services.web.sponsorblock import compute_ad_segments_expiry

_FETCHED_AT = datetime(2026, 6, 1, tzinfo=UTC)


def test_young_video_gets_short_ttl() -> None:
    expires_at = compute_ad_segments_expiry(video_age_days=1, fetched_at=_FETCHED_AT)
    assert expires_at == _FETCHED_AT + timedelta(days=3)


def test_month_old_video_gets_medium_ttl() -> None:
    expires_at = compute_ad_segments_expiry(video_age_days=20, fetched_at=_FETCHED_AT)
    assert expires_at == _FETCHED_AT + timedelta(days=14)


def test_settled_video_gets_long_ttl() -> None:
    expires_at = compute_ad_segments_expiry(video_age_days=90, fetched_at=_FETCHED_AT)
    assert expires_at == _FETCHED_AT + timedelta(days=60)


def test_very_old_video_gets_default_ttl() -> None:
    expires_at = compute_ad_segments_expiry(video_age_days=1000, fetched_at=_FETCHED_AT)
    assert expires_at == _FETCHED_AT + timedelta(days=180)


def test_expiry_is_anchored_to_fetched_at() -> None:
    other_fetch = _FETCHED_AT + timedelta(days=5)
    assert compute_ad_segments_expiry(1, other_fetch) == other_fetch + timedelta(days=3)
