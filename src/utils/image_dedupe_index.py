import functools
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import cast

from src.utils.cache import S3Cache

_IMAGE_DEDUPE_CACHE_DIR = ".cache/image-dedupe"
_IMAGE_DEDUPE_CACHE_PREFIX = "image-dedupe"


@functools.cache
def _image_dedupe_cache() -> S3Cache:
    return S3Cache(_IMAGE_DEDUPE_CACHE_DIR, _IMAGE_DEDUPE_CACHE_PREFIX)


@dataclass(frozen=True)
class HashDedupeEntry:
    file_hash: str
    canonical_key: str
    canonical_url: str
    output_ext: str
    source_bytes: int
    encoded_bytes: int
    seen_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class EpisodeDedupeEntry:
    author_slug: str
    episode_id: str
    file_hash: str
    canonical_url: str
    seen_at: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_key(file_hash: str) -> str:
    return f"thumb:hash:{file_hash}"


def _episode_key(author_slug: str, episode_id: str) -> str:
    return f"thumb:episode:{author_slug}:{episode_id}"


def _require_str(d: dict[str, object], key: str) -> str:
    v = d.get(key)
    if not isinstance(v, str):
        raise TypeError(key)
    return v


def _require_int(d: dict[str, object], key: str) -> int:
    v = d.get(key)
    if not isinstance(v, int):
        raise TypeError(key)
    return v


def _parse_hash_entry(value: dict[str, object]) -> HashDedupeEntry | None:
    try:
        return HashDedupeEntry(
            file_hash=_require_str(value, "file_hash"),
            canonical_key=_require_str(value, "canonical_key"),
            canonical_url=_require_str(value, "canonical_url"),
            output_ext=_require_str(value, "output_ext"),
            source_bytes=_require_int(value, "source_bytes"),
            encoded_bytes=_require_int(value, "encoded_bytes"),
            seen_at=_require_str(value, "seen_at"),
        )
    except TypeError:
        return None


def _parse_episode_entry(value: dict[str, object]) -> EpisodeDedupeEntry | None:
    try:
        return EpisodeDedupeEntry(
            author_slug=_require_str(value, "author_slug"),
            episode_id=_require_str(value, "episode_id"),
            file_hash=_require_str(value, "file_hash"),
            canonical_url=_require_str(value, "canonical_url"),
            seen_at=_require_str(value, "seen_at"),
        )
    except TypeError:
        return None


def remember_hash_dedupe(entry: HashDedupeEntry) -> None:
    _image_dedupe_cache().set(_hash_key(entry.file_hash), asdict(entry))


def remember_episode_dedupe(
    author_slug: str,
    episode_id: str,
    file_hash: str,
    canonical_url: str,
) -> None:
    payload = EpisodeDedupeEntry(
        author_slug=author_slug,
        episode_id=episode_id,
        file_hash=file_hash,
        canonical_url=canonical_url,
        seen_at=_utc_now_iso(),
    )
    _image_dedupe_cache().set(_episode_key(author_slug, episode_id), asdict(payload))


def get_hash_dedupe(file_hash: str) -> HashDedupeEntry | None:
    raw_value = _image_dedupe_cache().get(_hash_key(file_hash))
    if not isinstance(raw_value, dict):
        return None
    return _parse_hash_entry(cast(dict[str, object], raw_value))


def get_episode_dedupe(author_slug: str, episode_id: str) -> EpisodeDedupeEntry | None:
    raw_value = _image_dedupe_cache().get(_episode_key(author_slug, episode_id))
    if not isinstance(raw_value, dict):
        return None
    return _parse_episode_entry(cast(dict[str, object], raw_value))
