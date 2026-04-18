# cspell: words creepcast darknet gladwell smosh

import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from cachetools import LRUCache, cached

sys.path.insert(0, Path(__file__).parent.parent.as_posix())
from src.files.s3 import S3_ENDPOINT, get_file_list
from src.utils.regex import re_compile
from src.utils.text import create_slug, remove_control_chars

_TITLE_CACHE: LRUCache[Any, Any] = LRUCache(2048)


def _strip_suffix(pattern: str, episode: str) -> str:
    return re_compile(pattern).sub("", episode)


def _clean_darknet_diaries_title(filename: str) -> str:
    slug_name = create_slug(filename)
    match = re_compile(r"ep\-*(\d{1,3}[\-a-z0-9]+)$").search(slug_name)
    lst = list(match.groups() if match else [])
    lst = sorted(lst, key=len)
    return lst[-1].strip("-") if len(lst) else slug_name


def _clean_swindled_title(filename: str) -> str:
    _filename = re_compile(r"(?i)\s*\|\s*Audio Podcast$").sub("", filename)
    _filename = re_compile(r"(?i)\s*\|\s*Documentary$").sub("", _filename)
    title = re_compile(r"\(([^/\)]+)/[^)]*\)").sub(r"(\1)", _filename)
    return title.strip()


def _clean_behind_the_bastards_title(episode: str) -> str:
    return _strip_suffix(r"(?i)\| behind the bastards$", episode)


def _clean_coffee_break_swedish_title(episode: str) -> str:
    return _strip_suffix(r"(?i)\| coffee break swedish podcast$", episode)


def _clean_creepcast_title(episode: str) -> str:
    patterns = [
        r"(?i)\| creep cast$",
        r"(?i)\| creepcast$",
        r"(?i)\| creep tv$",
    ]
    for pattern in patterns:
        episode = _strip_suffix(pattern, episode)
    return episode


def _clean_financial_audit_title(episode: str) -> str:
    return _strip_suffix(r"(?i)\| financial audit$", episode)


def _clean_morbid_title(episode: str) -> str:
    patterns = [
        r"(?i)\| morbid$",
        r"(?i)\| morbid \| podcast$",
    ]
    for pattern in patterns:
        episode = _strip_suffix(pattern, episode)
    return episode


def _clean_revisionist_history_title(episode: str) -> str:
    return _strip_suffix(r"(?i)\| revisionist history malcolm gladwell$", episode)


def _clean_smosh_reads_reddit_stories_title(episode: str) -> str:
    return _strip_suffix(r"(?i)\| smosh reading reddit stories$", episode)


def _clean_stuff_they_dont_want_you_to_know_title(episode: str) -> str:
    return _strip_suffix(r"(?i)\| stuff they don't want you to know$", episode)


def _clean_stuff_you_should_know_title(episode: str) -> str:
    return _strip_suffix(r"(?i)\| stuff you should know$", episode)


_TITLE_CLEANERS = {
    "Behind the Bastards": _clean_behind_the_bastards_title,
    "Coffee Break Swedish": _clean_coffee_break_swedish_title,
    "CreepCast": _clean_creepcast_title,
    "Darknet Diaries": _clean_darknet_diaries_title,
    "Financial Audit": _clean_financial_audit_title,
    "Morbid": _clean_morbid_title,
    "Revisionist History": _clean_revisionist_history_title,
    "Smosh Reads Reddit Stories": _clean_smosh_reads_reddit_stories_title,
    "Stuff They Don't Want You To Know": _clean_stuff_they_dont_want_you_to_know_title,
    "Stuff You Should Know": _clean_stuff_you_should_know_title,
    "Swindled": _clean_swindled_title,
}


def _apply_title_cleaner(show: str, episode: str) -> str:
    cleaner = _TITLE_CLEANERS.get(show)
    if cleaner is None:
        return episode
    return cleaner(episode)


@cached(_TITLE_CACHE)
def normalize_title(show: str, episode: str) -> str:
    episode = remove_control_chars(episode)
    episode = _apply_title_cleaner(show, episode)
    return create_slug(episode).strip("-")


def get_s3_files(bucket: str, prefix: str) -> list[str]:
    file_list = get_file_list(bucket, prefix)
    root_path = Path(bucket) / prefix

    files: list[str] = []
    for file_key in file_list:
        filename = Path(file_key).name
        location = urljoin(S3_ENDPOINT, (root_path / filename).as_posix())
        files.append(location)

    return files
