from datetime import UTC, datetime
from pathlib import Path

import pytest

from adrift.adapters.process.storage.local_storage import LocalFilesystemStorage
from adrift.core.models import MediaMetadata
from adrift.core.models.storage_options import UploadOptions


@pytest.fixture(autouse=True)
def _rss_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RSS_BASE_URL", "https://cdn.example.com/")


def _storage(tmp_path: Path) -> LocalFilesystemStorage:
    return LocalFilesystemStorage(tmp_path)


def _metadata() -> MediaMetadata:
    return MediaMetadata(
        duration=12.5,
        source="https://youtube.com/watch?v=abc123",
        upload_date=datetime(2026, 4, 20, tzinfo=UTC),
        audio_hash="deadbeef",
        ad_segments=[(0.0, 15.0), (120.5, 145.25)],
        ad_segments_expires_at=datetime(2026, 6, 1, tzinfo=UTC),
    )


def test_upload_file_writes_identical_bytes_and_returns_url(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    src = tmp_path / "source.opus"
    src.write_bytes(b"episode audio bytes")

    url = storage.upload_file(("media", "podcasts/show/ep1.opus"), src)

    dest = tmp_path / "media" / "podcasts" / "show" / "ep1.opus"
    assert dest.read_bytes() == b"episode audio bytes"
    assert url == "https://cdn.example.com/podcasts/show/ep1.opus"


def test_upload_file_leaves_no_temp_files_behind(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    src = tmp_path / "source.opus"
    src.write_bytes(b"episode audio bytes")

    storage.upload_file(("media", "podcasts/show/ep1.opus"), src)

    remaining = list((tmp_path / "media" / "podcasts" / "show").iterdir())
    assert remaining == [tmp_path / "media" / "podcasts" / "show" / "ep1.opus"]


def test_upload_file_with_metadata_round_trips_through_sidecar(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    src = tmp_path / "source.opus"
    src.write_bytes(b"episode audio bytes")
    metadata = _metadata()

    storage.upload_file(("media", "podcasts/show/ep1.opus"), src, UploadOptions(metadata=metadata))

    round_tripped = storage.get_metadata("media", "podcasts/show/ep1.opus")
    assert round_tripped == metadata


def test_get_metadata_returns_none_when_sidecar_missing(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    assert storage.get_metadata("media", "podcasts/show/missing.opus") is None


def test_get_metadata_returns_none_when_sidecar_is_corrupt(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    sidecar = tmp_path / "media" / "podcasts" / "show" / "ep1.opus.meta.json"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text("not json")

    assert storage.get_metadata("media", "podcasts/show/ep1.opus") is None


def test_exists_matches_extension_agnostic_by_default(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    src = tmp_path / "source.opus"
    src.write_bytes(b"data")
    storage.upload_file(("media", "podcasts/show/episode.opus"), src)

    assert storage.exists("media", "podcasts/show/episode") == "episode.opus"


def test_exists_requires_exact_name_when_not_extension_agnostic(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    src = tmp_path / "source.opus"
    src.write_bytes(b"data")
    storage.upload_file(("media", "podcasts/show/episode.opus"), src)

    assert storage.exists("media", "podcasts/show/episode", extension_agnostic=False) is None
    assert (
        storage.exists("media", "podcasts/show/episode.opus", extension_agnostic=False)
        == "episode.opus"
    )


def test_exists_returns_none_when_missing(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    assert storage.exists("media", "podcasts/show/nope") is None


def test_get_file_list_excludes_sidecars_and_subdirectories(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    src = tmp_path / "source.opus"
    src.write_bytes(b"data")
    storage.upload_file(
        ("media", "podcasts/show/ep1.opus"), src, UploadOptions(metadata=_metadata())
    )
    (tmp_path / "media" / "podcasts" / "show" / "subdir").mkdir()

    assert storage.get_file_list("media", "podcasts/show") == ["ep1.opus"]


def test_get_file_list_without_extensions(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    src = tmp_path / "source.opus"
    src.write_bytes(b"data")
    storage.upload_file(("media", "podcasts/show/ep1.opus"), src)

    assert storage.get_file_list("media", "podcasts/show", without_extensions=True) == ["ep1"]


def test_delete_removes_file_and_sidecar(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    src = tmp_path / "source.opus"
    src.write_bytes(b"data")
    storage.upload_file(
        ("media", "podcasts/show/ep1.opus"), src, UploadOptions(metadata=_metadata())
    )

    storage.delete("media", "podcasts/show/ep1.opus")

    assert storage.get_file_list("media", "podcasts/show") == []
    assert storage.get_metadata("media", "podcasts/show/ep1.opus") is None


def test_delete_is_a_no_op_when_key_missing(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    storage.delete("media", "podcasts/show/nope.opus")


def test_get_public_urls_raises_when_rss_base_url_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = _storage(tmp_path)
    src = tmp_path / "source.opus"
    src.write_bytes(b"data")
    storage.upload_file(("media", "podcasts/show/ep1.opus"), src)

    monkeypatch.delenv("RSS_BASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        storage.get_public_urls("media", "podcasts/show")


def test_get_public_urls_builds_well_formed_urls(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    src = tmp_path / "source.opus"
    src.write_bytes(b"data")
    storage.upload_file(("media", "podcasts/show/ep1.opus"), src)

    assert storage.get_public_urls("media", "podcasts/show") == [
        "https://cdn.example.com/podcasts/show/ep1.opus"
    ]
