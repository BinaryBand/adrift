from datetime import datetime, timezone

from src.app_common import PodcastConfig
from src.models.metadata import RssEpisode
from src.models.pipeline import DownloadEpisode
from src.orchestration.download_service import build_download_queue


def _episode(title: str, pub_date: datetime | None = None) -> DownloadEpisode:
    return DownloadEpisode(
        episode=RssEpisode(
            id=title,
            title=title,
            author="CreepCast",
            content=f"https://youtube.com/watch?v={title}",
            pub_date=pub_date,
        ),
        sponsor_segments=[],
        video_id="video-id",
    )


def _config() -> PodcastConfig:
    return PodcastConfig(
        name="CreepCast",
        path="/media/podcasts/creepcast",
        references=[],
        downloads=[],
    )


def test_build_download_queue_prioritizes_missing_then_newest(monkeypatch) -> None:
    newest_missing = _episode("Newest Missing", datetime(2026, 4, 20, tzinfo=timezone.utc))
    older_missing = _episode("Older Missing", datetime(2026, 4, 10, tzinfo=timezone.utc))
    newest_existing = _episode("Newest Existing", datetime(2026, 4, 21, tzinfo=timezone.utc))

    existing_titles = {"Newest Existing"}

    def _exists_on_s3(ep, config):
        del config
        return ep.episode.title in existing_titles

    monkeypatch.setattr(
        "src.orchestration.download_service._episode_exists_on_s3",
        _exists_on_s3,
    )

    queue = build_download_queue([older_missing, newest_existing, newest_missing], _config())

    assert [item.episode.episode.title for item in queue] == [
        "Newest Missing",
        "Older Missing",
        "Newest Existing",
    ]


def test_build_download_queue_preserves_unknown_dates_after_dated_missing(monkeypatch) -> None:
    dated_missing = _episode("Dated Missing", datetime(2026, 4, 20, tzinfo=timezone.utc))
    undated_missing = _episode("Undated Missing")

    monkeypatch.setattr(
        "src.orchestration.download_service._episode_exists_on_s3",
        lambda ep, config: False,
    )

    queue = build_download_queue([undated_missing, dated_missing], _config())

    assert [item.episode.episode.title for item in queue] == [
        "Dated Missing",
        "Undated Missing",
    ]
