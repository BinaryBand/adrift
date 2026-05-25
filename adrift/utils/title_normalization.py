# cspell: words creepcast darknet gladwell smosh

from dataclasses import dataclass
from typing import Any, Callable

from cachetools import LRUCache, cached

from adrift.utils.regex import re_compile
from adrift.utils.text import create_slug, remove_control_chars

_TITLE_CACHE: LRUCache[Any, Any] = LRUCache(2048)


def _strip_suffix(pattern: str, episode: str) -> str:
    return re_compile(pattern).sub("", episode)


def _clean_darknet_diaries_title(filename: str) -> str:
    slug_name = create_slug(filename)
    match = re_compile(r"ep\-*(\d{1,3}[\-a-z0-9]+)$").search(slug_name)
    groups = [str(g) for g in (match.groups() if match else [])]
    groups = sorted(groups, key=len)
    return str(groups[-1]).strip("-") if groups else slug_name


def _clean_swindled_title(filename: str) -> str:
    cleaned_filename = re_compile(r"(?i)\s*\|\s*Audio Podcast$").sub("", filename)
    cleaned_filename = re_compile(r"(?i)\s*\|\s*Documentary$").sub("", cleaned_filename)
    title = re_compile(r"\(([^/\)]+)/[^)]*\)").sub(r"(\1)", cleaned_filename)
    return title.strip()


@dataclass(frozen=True)
class _ShowRule:
    prefix_patterns: tuple[str, ...] = ()
    suffix_patterns: tuple[str, ...] = ()
    slug_suffixes: tuple[str, ...] = ()
    cleaner: Callable[[str], str] | None = None


_SHOW_RULES = {
    "Behind the Bastards": _ShowRule(
        suffix_patterns=(r"(?i)\| behind the bastards$",),
        slug_suffixes=("Behind the Bastards",),
    ),
    "Coffee Break Swedish": _ShowRule(
        suffix_patterns=(r"(?i)\| coffee break swedish podcast$",),
        slug_suffixes=("Coffee Break Swedish Podcast",),
    ),
    "CreepCast": _ShowRule(
        suffix_patterns=(r"(?i)\| creep cast$", r"(?i)\| creepcast$", r"(?i)\| creep tv$"),
        slug_suffixes=("Creep Cast", "CreepCast", "Creep TV"),
    ),
    "Darknet Diaries": _ShowRule(cleaner=_clean_darknet_diaries_title),
    "Financial Audit": _ShowRule(
        suffix_patterns=(r"(?i)\| financial audit$",),
        slug_suffixes=("Financial Audit",),
    ),
    "Morbid": _ShowRule(
        prefix_patterns=(
            r"(?i)^episode(?:\s+|\-+)\d{1,3}[:\-]?\s*",
            r"(?i)^fan favorite:\s*",
            r"(?i)^episode revisit:\s*",
        ),
        suffix_patterns=(
            r"(?i)\|\s*morbid:\s*a true crime podcast$",
            r"(?i)\|\s*morbid\s*\|\s*podcast\s*\|\s*video$",
            r"(?i)\|\s*morbid\s*\|\s*podcast$",
            r"(?i)\|\s*morbid\|\s*podcast$",
            r"(?i)\|\s*morbid$",
            r"(?i)\|\s*episode\s+\d+\s*$",
        ),
        slug_suffixes=("Morbid", "Morbid Podcast", "Morbid A True Crime Podcast"),
    ),
    "Revisionist History": _ShowRule(
        suffix_patterns=(r"(?i)\| revisionist history malcolm gladwell$",),
        slug_suffixes=("Revisionist History Malcolm Gladwell",),
    ),
    "Smosh Reads Reddit Stories": _ShowRule(
        suffix_patterns=(r"(?i)\| smosh reading reddit stories$",),
        slug_suffixes=("Smosh Reading Reddit Stories",),
    ),
    "Stuff They Don't Want You To Know": _ShowRule(
        suffix_patterns=(r"(?i)\| stuff they don't want you to know$",),
        slug_suffixes=("Stuff They Don't Want You To Know",),
    ),
    "Stuff You Should Know": _ShowRule(
        suffix_patterns=(r"(?i)\| stuff you should know$",),
        slug_suffixes=("Stuff You Should Know",),
    ),
    "Swindled": _ShowRule(cleaner=_clean_swindled_title),
}


def _apply_show_rules(show: str, episode: str) -> str:
    rule = _SHOW_RULES.get(show)
    if rule is None:
        return episode

    if rule.cleaner is not None:
        episode = rule.cleaner(episode)

    for pattern in rule.prefix_patterns:
        episode = re_compile(pattern).sub("", episode)

    for pattern in rule.suffix_patterns:
        episode = _strip_suffix(pattern, episode)

    return episode


def _strip_slug_suffixes(show: str, slug: str) -> str:
    rule = _SHOW_RULES.get(show)
    if rule is None:
        return slug.strip("-")
    for suffix in rule.slug_suffixes:
        suffix_slug = create_slug(suffix).strip("-")
        if slug.endswith(f"-{suffix_slug}"):
            slug = slug[: -len(suffix_slug) - 1]
    return slug.strip("-")


@cached(_TITLE_CACHE)
def normalize_title(show: str, episode: str) -> str:
    episode = remove_control_chars(episode)
    episode = _apply_show_rules(show, episode)
    return _strip_slug_suffixes(show, create_slug(episode).strip("-"))


__all__ = ["normalize_title"]
