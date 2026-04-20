from datetime import datetime, timezone

from src.app_common import PodcastConfig
from src.models import MediaMetadata
from src.models.metadata import RssEpisode
from src.models.pipeline import DownloadEpisode
from src.orchestration.download_service import (
    DownloadProgressHooks,
    _episode_exists_on_s3,
    _process_in_tmpdir,
    build_download_queue,
)


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


def test_episode_exists_on_s3_matches_existing_youtube_video_id(monkeypatch) -> None:
    episode = DownloadEpisode(
        episode=RssEpisode(
            id="new-title",
            title="New YouTube Title",
            author="CreepCast",
            content="https://youtube.com/watch?v=stable-video-id",
            pub_date=datetime(2026, 4, 20, tzinfo=timezone.utc),
        ),
        sponsor_segments=[],
        video_id="stable-video-id",
    )
    config = _config()

    monkeypatch.setattr("src.orchestration.download_service.exists", lambda bucket, key: None)
    monkeypatch.setattr(
        "src.orchestration.download_service.get_file_list",
        lambda bucket, prefix, without_extensions=False: ["old-title.opus"],
    )
    monkeypatch.setattr(
        "src.orchestration.download_service.get_metadata",
        lambda bucket, key: MediaMetadata(
            duration=1.0,
            source="https://youtube.com/watch?v=stable-video-id",
            upload_date=datetime(2026, 4, 19, tzinfo=timezone.utc),
            sponsors_removed=False,
        ),
    )
    from src.orchestration import download_service

    download_service._existing_media_sources.cache_clear()

    assert _episode_exists_on_s3(episode, config) is True


def test_episode_exists_on_s3_matches_existing_direct_source_url(monkeypatch) -> None:
    episode = DownloadEpisode(
        episode=RssEpisode(
            id="direct-id",
            title="Renamed Direct Source",
            author="Test Show",
            content="https://cdn.example.com/audio/episode.mp3",
            pub_date=datetime(2026, 4, 20, tzinfo=timezone.utc),
        ),
        sponsor_segments=[],
        video_id=None,
    )
    config = PodcastConfig(
        name="Test Show",
        path="/media/podcasts/test-show",
        references=[],
        downloads=[],
    )

    monkeypatch.setattr("src.orchestration.download_service.exists", lambda bucket, key: None)
    monkeypatch.setattr(
        "src.orchestration.download_service.get_file_list",
        lambda bucket, prefix, without_extensions=False: ["old-direct-title.opus"],
    )
    monkeypatch.setattr(
        "src.orchestration.download_service.get_metadata",
        lambda bucket, key: MediaMetadata(
            duration=1.0,
            source="https://cdn.example.com/audio/episode.mp3",
            upload_date=datetime(2026, 4, 19, tzinfo=timezone.utc),
            sponsors_removed=False,
        ),
    )
    from src.orchestration import download_service

    download_service._existing_media_sources.cache_clear()

    assert _episode_exists_on_s3(episode, config) is True


def test_process_in_tmpdir_reports_upload_progress(monkeypatch, tmp_path) -> None:
    episode = _episode("Upload Progress")
    config = _config()
    audio_path = tmp_path / "audio.m4a"
    opus_path = tmp_path / "audio.opus"
    audio_path.write_bytes(b"audio")
    opus_path.write_bytes(b"opus")

    operations: list[str] = []
    updates: list[tuple[int, int | None]] = []

    monkeypatch.setattr(
        "src.orchestration.download_service._s3_prefix",
        lambda config: ("bucket", "podcasts/creepcast"),
    )
    monkeypatch.setattr(
        "src.orchestration.download_service._download_audio",
        lambda ep, dest, callback=None: audio_path,
    )
    monkeypatch.setattr(
        "src.orchestration.download_service.convert_to_opus",
        lambda audio, callback=None: opus_path,
    )
    monkeypatch.setattr("src.orchestration.download_service.get_duration", lambda path: 42.0)

    captured: dict[str, object] = {}

    def _upload_file(bucket, key, file_path, options):
        captured["bucket"] = bucket
        captured["key"] = key
        captured["file_path"] = file_path
        captured["options"] = options
        assert options is not None
        assert options.callback is not None
        options.callback(3, 10)

    monkeypatch.setattr("src.orchestration.download_service.upload_file", _upload_file)

    hooks = DownloadProgressHooks(
        on_operation=operations.append,
        on_progress=lambda current, total: updates.append((current, total)),
        on_complete=lambda: operations.append("<cleared>"),
    )

    uploaded = _process_in_tmpdir(episode, config, tmp_path, hooks)

    assert uploaded is True
    assert operations == [
        "download audio: Upload Progress",
        "convert opus: Upload Progress",
        "upload opus: Upload Progress",
        "<cleared>",
    ]
    assert updates == [(3, 10)]
    options = captured["options"]
    assert isinstance(options, object)
    assert captured["bucket"] == "bucket"
    assert captured["key"] == "podcasts/creepcast/upload-progress.opus"
    assert captured["file_path"] == opus_path
