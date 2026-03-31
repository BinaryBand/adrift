from cachetools import LRUCache, cached
from urllib.parse import urljoin
from pathlib import Path
import sys

sys.path.insert(0, Path(__file__).parent.parent.as_posix())
from src.files.s3 import S3_ENDPOINT, get_file_list
from src.utils.regex import re_compile
from src.utils.text import create_slug, remove_control_chars


_TITLE_CACHE: LRUCache = LRUCache(2048)


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


@cached(_TITLE_CACHE)
def normalize_title(show: str, episode: str) -> str:
    episode = remove_control_chars(episode)
    episode = re_compile(r"__adless").sub("", episode)

    # cspell:disable
    if show == "Behind the Bastards":
        episode = re_compile(r"(?i)\| behind the bastards$").sub("", episode)
    if show == "Coffee Break Swedish":
        episode = re_compile(r"(?i)\| coffee break swedish podcast$").sub("", episode)
    if show == "CreepCast":
        episode = re_compile(r"(?i)\| creep cast$").sub("", episode)
        episode = re_compile(r"(?i)\| creepcast$").sub("", episode)
        episode = re_compile(r"(?i)\| creep tv$").sub("", episode)
    if show == "Darknet Diaries":
        episode = _clean_darknet_diaries_title(episode)
    if show == "Financial Audit":
        episode = re_compile(r"(?i)\| financial audit$").sub("", episode)
    if show == "Revisionist History":
        episode = re_compile(r"(?i)\| revisionist history malcolm gladwell$").sub(
            "", episode
        )
    if show == "Smosh Reads Reddit Stories":
        episode = re_compile(r"(?i)\| smosh reading reddit stories$").sub("", episode)
    if show == "Stuff They Don't Want You To Know":
        episode = re_compile(r"(?i)\| stuff they don't want you to know$").sub(
            "", episode
        )
    if show == "Stuff You Should Know":
        episode = re_compile(r"(?i)\| stuff you should know$").sub("", episode)
    if show == "Swindled":
        episode = _clean_swindled_title(episode)
    # cspell:enable

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
