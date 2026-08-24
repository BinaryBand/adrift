"""Per-podcast title and slug normalization rules."""

# cspell: words creepcast darknet gladwell smosh
import pathlib
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from diskcache import Cache

from adrift.core.util.regex import re_compile
from adrift.core.util.text import create_slug, remove_control_chars

_TITLE_DISK_CACHE = Cache(str(pathlib.Path(".cache/title_normalization").resolve()))
_CACHE_CONFIG_MTIME_KEY = "__config_mtime__"


def _strip_suffix(pattern: str, episode: str) -> str:
    return re_compile(pattern).sub("", episode)


@dataclass(frozen=True)
class _RegexReplacement:
    target: str
    pattern: str
    replacement: str


@dataclass(frozen=True)
class _ShowRule:
    prefix_patterns: tuple[str, ...] = ()
    suffix_patterns: tuple[str, ...] = ()
    slug_suffixes: tuple[str, ...] = ()
    replacements: tuple[_RegexReplacement, ...] = ()


def _coerce_replacement_rules(value: object) -> tuple[_RegexReplacement, ...]:
    if not isinstance(value, list):
        return ()
    rules: list[_RegexReplacement] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        target = item.get("target", "title")
        pattern = item.get("pattern")
        replacement = item.get("replacement")
        if isinstance(target, str) and isinstance(pattern, str) and isinstance(replacement, str):
            rules.append(_RegexReplacement(target=target, pattern=pattern, replacement=replacement))
    return tuple(rules)


def _coerce_str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _title_normalization_dict(podcast: dict[str, Any]) -> dict[str, Any] | None:
    cleanup = podcast.get("cleanup")
    if not isinstance(cleanup, dict):
        return None
    title_norm = cleanup.get("title_normalization")
    if not isinstance(title_norm, dict):
        return None
    return title_norm


def _parse_single_podcast(podcast: dict[str, Any], rules: dict[str, _ShowRule]) -> None:
    name = podcast.get("name")
    if not isinstance(name, str):
        return

    title_norm = _title_normalization_dict(podcast)
    if not isinstance(title_norm, dict):
        return

    prefix_patterns = _coerce_str_tuple(title_norm.get("prefix_patterns"))
    suffix_patterns = _coerce_str_tuple(title_norm.get("suffix_patterns"))
    slug_suffixes = _coerce_str_tuple(title_norm.get("slug_suffixes"))
    replacements = _coerce_replacement_rules(title_norm.get("replacements"))

    rules[name] = _ShowRule(
        prefix_patterns=prefix_patterns,
        suffix_patterns=suffix_patterns,
        slug_suffixes=slug_suffixes,
        replacements=replacements,
    )


_CONFIG_DIR = pathlib.Path("static/config")
_CONFIG_LOAD_ERRORS = (OSError, tomllib.TOMLDecodeError)


def _config_paths() -> list[pathlib.Path]:
    """Return every podcast config file, not just ``podcasts.toml``.

    Shows are split across several TOML files (``youtube.toml`` and friends);
    reading only one of them silently drops the cleanup rules defined in the
    others. The rest of the codebase already globs -- see the
    ``static/config/*.toml`` targets in core/services/app_common.py.
    """
    try:
        return sorted(_CONFIG_DIR.glob("*.toml"))
    except OSError:
        return []


def _load_show_rules() -> dict[str, _ShowRule]:
    rules: dict[str, _ShowRule] = {}
    for path in _config_paths():
        try:
            with path.open("rb") as f:
                config = tomllib.load(f)
        except _CONFIG_LOAD_ERRORS:
            continue

        podcasts = config.get("podcasts")
        if not isinstance(podcasts, list):
            continue

        for podcast in podcasts:
            if isinstance(podcast, dict):
                _parse_single_podcast(podcast, rules)

    return rules


_SHOW_RULES = _load_show_rules()


def _config_mtime() -> float:
    # max() over every config file, not just one: the disk cache keys off this,
    # so a single-path mtime goes stale when only youtube.toml changes.
    mtimes: list[float] = []
    for path in _config_paths():
        try:
            mtimes.append(path.stat().st_mtime)
        except OSError:
            continue
    return max(mtimes, default=0.0)


def _invalidate_title_cache_if_stale() -> None:
    current = _config_mtime()
    if _TITLE_DISK_CACHE.get(_CACHE_CONFIG_MTIME_KEY) != current:
        _TITLE_DISK_CACHE.clear()
        _TITLE_DISK_CACHE.set(_CACHE_CONFIG_MTIME_KEY, current)


_invalidate_title_cache_if_stale()


def _apply_show_rules(show: str, episode: str) -> str:
    rule = _SHOW_RULES.get(show)
    if rule is None:
        return episode

    for repl in rule.replacements:
        if repl.target == "title":
            episode = re_compile(repl.pattern).sub(repl.replacement, episode)

    for pattern in rule.prefix_patterns:
        episode = re_compile(pattern).sub("", episode)

    for pattern in rule.suffix_patterns:
        episode = _strip_suffix(pattern, episode)

    return episode


def _strip_slug_suffixes(show: str, slug: str) -> str:
    rule = _SHOW_RULES.get(show)
    if rule is None:
        return slug.strip("-")

    for repl in rule.replacements:
        if repl.target == "slug":
            slug = re_compile(repl.pattern).sub(repl.replacement, slug)

    for suffix in rule.slug_suffixes:
        suffix_slug = create_slug(suffix).strip("-")
        if slug.endswith(f"-{suffix_slug}"):
            slug = slug[: -len(suffix_slug) - 1]
    return slug.strip("-")


@lru_cache(maxsize=2048)
def normalize_title(show: str, episode: str) -> str:
    """Return the normalized episode title for ``show`` (memoized on disk)."""
    key = (show, episode)
    cached: str | None = _TITLE_DISK_CACHE.get(key)
    if cached is not None:
        return cached
    result = _compute_normalize_title(show, episode)
    _TITLE_DISK_CACHE.set(key, result)
    return result


def _compute_normalize_title(show: str, episode: str) -> str:
    episode = remove_control_chars(episode)
    episode = _apply_show_rules(show, episode)
    return _strip_slug_suffixes(show, create_slug(episode).strip("-"))


__all__ = ["normalize_title"]
