import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())

from src.utils.image_dedupe_index import (
    EpisodeDedupeEntry,
    HashDedupeEntry,
    get_episode_dedupe,
    get_hash_dedupe,
    remember_episode_dedupe,
    remember_hash_dedupe,
)


class _FakeCache:
    def __init__(self):
        self._store: dict[str, object] = {}

    def get(self, key: str, default: object = None) -> object:
        return self._store.get(key, default)

    def set(self, key: str, value: object, expire: int | None = None) -> None:
        del expire
        self._store[key] = value


def test_get_hash_dedupe_returns_none_for_missing_entry() -> None:
    fake_cache = _FakeCache()
    with patch("src.utils.image_dedupe_index._image_dedupe_cache", return_value=fake_cache):
        assert get_hash_dedupe("missing") is None


def test_hash_dedupe_roundtrip() -> None:
    fake_cache = _FakeCache()
    with patch("src.utils.image_dedupe_index._image_dedupe_cache", return_value=fake_cache):
        remember_hash_dedupe(
            HashDedupeEntry(
                file_hash="deadbeef",
                canonical_key="podcasts/_thumbs/by-hash/deadbeef.webp",
                canonical_url="https://s3.example.com/media/podcasts/_thumbs/by-hash/deadbeef.webp",
                output_ext=".webp",
                source_bytes=12_000,
                encoded_bytes=4_000,
            )
        )

        entry = get_hash_dedupe("deadbeef")

    assert isinstance(entry, HashDedupeEntry)
    assert entry.file_hash == "deadbeef"
    assert entry.output_ext == ".webp"
    assert entry.source_bytes == 12_000
    assert entry.encoded_bytes == 4_000


def test_episode_dedupe_roundtrip() -> None:
    fake_cache = _FakeCache()
    with patch("src.utils.image_dedupe_index._image_dedupe_cache", return_value=fake_cache):
        remember_episode_dedupe(
            author_slug="test-author",
            episode_id="ep-42",
            file_hash="deadbeef",
            canonical_url="https://s3.example.com/media/podcasts/_thumbs/by-hash/deadbeef.webp",
        )

        entry = get_episode_dedupe("test-author", "ep-42")

    assert isinstance(entry, EpisodeDedupeEntry)
    assert entry.author_slug == "test-author"
    assert entry.episode_id == "ep-42"
    assert entry.file_hash == "deadbeef"
