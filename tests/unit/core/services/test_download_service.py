import hashlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from adrift.core.models import DownloadEpisode, MediaMetadata, PodcastConfig, RssEpisode
from adrift.core.ports import InMemoryCache
from adrift.core.services.context import AppContext, EventBus
from adrift.core.services.download_process import (
    build_download_queue,
    episode_exists_in_storage,
    process_in_tmpdir,
)
from adrift.core.services.events import DownloadCompleted, OperationStarted, ProgressUpdated


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


def _ctx() -> AppContext:
    return _ctx_with_storage(SimpleNamespace())


def _ctx_with_storage(storage: object) -> AppContext:
    return AppContext(
        storage=storage,
        secrets=SimpleNamespace(source_name="test", get=lambda _key, default="": default),
        rss_cache=InMemoryCache(),
        yt_cache=InMemoryCache(),
        event_bus=EventBus(),
    )


def test_build_download_queue_prioritizes_missing_then_newest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    newest_missing = _episode("Newest Missing", datetime(2026, 4, 20, tzinfo=UTC))
    older_missing = _episode("Older Missing", datetime(2026, 4, 10, tzinfo=UTC))
    newest_existing = _episode("Newest Existing", datetime(2026, 4, 21, tzinfo=UTC))

    existing_titles = {"Newest Existing"}

    def _exists_in_storage(ep: DownloadEpisode, config: PodcastConfig, ctx: AppContext) -> bool:
        del config
        del ctx
        return ep.episode.title in existing_titles

    monkeypatch.setattr(
        "adrift.core.services.download_process.episode_exists_in_storage",
        _exists_in_storage,
    )

    queue = build_download_queue(
        [older_missing, newest_existing, newest_missing],
        _config(),
        _ctx(),
    )

    assert [item.episode.episode.title for item in queue] == [
        "Newest Missing",
        "Older Missing",
        "Newest Existing",
    ]


def test_build_download_queue_preserves_unknown_dates_after_dated_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dated_missing = _episode("Dated Missing", datetime(2026, 4, 20, tzinfo=UTC))
    undated_missing = _episode("Undated Missing")

    def _always_missing(ep: DownloadEpisode, config: PodcastConfig, ctx: AppContext) -> bool:
        del ep
        del config
        del ctx
        return False

    monkeypatch.setattr(
        "adrift.core.services.download_process.episode_exists_in_storage",
        _always_missing,
    )

    queue = build_download_queue([undated_missing, dated_missing], _config(), _ctx())

    assert [item.episode.episode.title for item in queue] == [
        "Dated Missing",
        "Undated Missing",
    ]


def test_episode_exists_in_storage_matches_existing_youtube_video_id() -> None:
    episode = DownloadEpisode(
        episode=RssEpisode(
            id="new-title",
            title="New YouTube Title",
            author="CreepCast",
            content="https://youtube.com/watch?v=stable-video-id",
            pub_date=datetime(2026, 4, 20, tzinfo=UTC),
        ),
        sponsor_segments=[],
        video_id="stable-video-id",
    )
    config = _config()

    fake = SimpleNamespace()
    fake.exists = lambda _bucket, _key, **_kwargs: None
    fake.get_file_list = lambda _bucket, _prefix, **_kwargs: ["old-title.opus"]
    fake.get_metadata = lambda _bucket, _key: MediaMetadata(
        duration=1.0,
        source="https://youtube.com/watch?v=stable-video-id",
        upload_date=datetime(2026, 4, 19, tzinfo=UTC),
    )
    assert episode_exists_in_storage(episode, config, _ctx_with_storage(fake)) is True


def test_episode_exists_in_storage_matches_existing_direct_source_url() -> None:
    episode = DownloadEpisode(
        episode=RssEpisode(
            id="direct-id",
            title="Renamed Direct Source",
            author="Test Show",
            content="https://cdn.example.com/audio/episode.mp3",
            pub_date=datetime(2026, 4, 20, tzinfo=UTC),
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

    fake = SimpleNamespace()
    fake.exists = lambda _bucket, _key, **_kwargs: None
    fake.get_file_list = lambda _bucket, _prefix, **_kwargs: ["old-direct-title.opus"]
    fake.get_metadata = lambda _bucket, _key: MediaMetadata(
        duration=1.0,
        source="https://cdn.example.com/audio/episode.mp3",
        upload_date=datetime(2026, 4, 19, tzinfo=UTC),
    )
    assert episode_exists_in_storage(episode, config, _ctx_with_storage(fake)) is True


def test_episode_exists_in_storage_matches_cleaned_existing_filename() -> None:
    episode = DownloadEpisode(
        episode=RssEpisode(
            id="morbid-title",
            title="Ann & Billy Woodward",
            author="Morbid",
            content="https://youtube.com/watch?v=woodward-video",
            pub_date=datetime(2026, 4, 20, tzinfo=UTC),
        ),
        sponsor_segments=[],
        video_id="woodward-video",
    )
    config = PodcastConfig(
        name="Morbid",
        path="/media/podcasts/morbid",
        references=[],
        downloads=[],
    )

    fake = SimpleNamespace()
    fake.exists = lambda _bucket, _key, **_kwargs: None
    fake.get_file_list = lambda _bucket, _prefix, **_kwargs: [
        "ann-billy-woodward-morbid-podcast.opus"
    ]
    fake.get_metadata = lambda _bucket, _key: None
    assert episode_exists_in_storage(episode, config, _ctx_with_storage(fake)) is True


def test_process_in_tmpdir_reports_upload_progress(  # noqa: PLR0915
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    episode = _episode("Upload Progress")
    config = _config()
    audio_path = tmp_path / "audio.m4a"
    opus_path = tmp_path / "audio.opus"
    audio_path.write_bytes(b"audio")
    opus_path.write_bytes(b"opus")

    operations: list[str] = []
    updates: list[tuple[int, int | None]] = []
    completions: list[str] = []

    def _storage_prefix_fn(_cfg: PodcastConfig) -> tuple[str, str]:
        return ("bucket", "podcasts/creepcast")

    def _download_audio_fn(_ep: DownloadEpisode, _dest: Path, _ctx: object | None = None) -> Path:
        return audio_path

    def _convert_to_opus_fn(_audio: Path, callback: object | None = None) -> Path:  # noqa: ARG001
        return opus_path

    def _get_duration_fn(_path: Path) -> float:
        return 42.0

    monkeypatch.setattr(
        "adrift.core.services.download_process.storage_prefix",
        _storage_prefix_fn,
    )
    monkeypatch.setattr(
        "adrift.core.services.download_process._download_audio",
        _download_audio_fn,
    )
    monkeypatch.setattr(
        "adrift.core.services.download_process.convert_to_opus",
        _convert_to_opus_fn,
    )
    monkeypatch.setattr(
        "adrift.core.services.download_process.get_duration",
        _get_duration_fn,
    )

    captured: dict[str, object] = {}

    def _upload_file(bucket: str, key: str, file_path: Path, options: object | None) -> None:
        captured["bucket"] = bucket
        captured["key"] = key
        captured["file_path"] = file_path
        captured["options"] = options
        assert options is not None
        assert options.callback is not None
        # mypy/pyright can't infer the callable shape here; call dynamically
        options.callback(3, 10)  # type: ignore[union-attr]

    fake = SimpleNamespace()
    fake.upload_file = lambda bucket_key, file_path, options: _upload_file(
        bucket_key[0], bucket_key[1], file_path, options
    )
    ctx = _ctx_with_storage(fake)
    ctx.event_bus.subscribe(OperationStarted, lambda event: operations.append(event.label))
    ctx.event_bus.subscribe(
        ProgressUpdated,
        lambda event: updates.append((event.current, event.total)),
    )
    ctx.event_bus.subscribe(DownloadCompleted, lambda event: completions.append(event.storage_key))

    uploaded = process_in_tmpdir(episode, config, tmp_path, ctx)

    assert uploaded is True
    assert operations == [
        "download audio: Upload Progress",
        "convert opus: Upload Progress",
        "upload opus: Upload Progress",
    ]
    assert updates == [(3, 10)]
    assert completions == ["podcasts/creepcast/upload-progress.opus"]
    metadata = captured["options"].metadata  # type: ignore[union-attr]
    assert isinstance(metadata, MediaMetadata)
    assert metadata.audio_hash == hashlib.sha256(b"opus").hexdigest()
    assert metadata.ad_segments == []
    assert metadata.ad_segments_expires_at is None


def test_process_in_tmpdir_sets_ad_segments_expiry_when_segments_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    episode = _episode("Sponsor Segments", pub_date=datetime(2020, 1, 1, tzinfo=UTC))
    episode.sponsor_segments = [(0.0, 30.0)]
    config = _config()
    audio_path = tmp_path / "audio.m4a"
    opus_path = tmp_path / "audio.opus"
    audio_path.write_bytes(b"audio")
    opus_path.write_bytes(b"opus")

    monkeypatch.setattr(
        "adrift.core.services.download_process.storage_prefix",
        lambda _cfg: ("bucket", "podcasts/creepcast"),
    )
    monkeypatch.setattr(
        "adrift.core.services.download_process._download_audio",
        lambda _ep, _dest, _ctx=None: audio_path,
    )
    monkeypatch.setattr(
        "adrift.core.services.download_process.convert_to_opus",
        lambda _audio, callback=None: opus_path,  # noqa: ARG005
    )
    monkeypatch.setattr(
        "adrift.core.services.download_process.get_duration",
        lambda _path: 42.0,
    )

    captured: dict[str, object] = {}

    def _upload_file(
        _bucket_key: tuple[str, str], _file_path: Path, options: object | None
    ) -> None:
        captured["options"] = options

    fake = SimpleNamespace()
    fake.upload_file = _upload_file
    ctx = _ctx_with_storage(fake)

    assert process_in_tmpdir(episode, config, tmp_path, ctx) is True

    metadata = captured["options"].metadata  # type: ignore[union-attr]
    assert isinstance(metadata, MediaMetadata)
    assert metadata.ad_segments == [(0.0, 30.0)]
    assert metadata.ad_segments_expires_at is not None
    assert metadata.ad_segments_expires_at > datetime.now(tz=UTC)
