from functools import lru_cache

from unidecode import unidecode

# from src.app_common import load_static_config
from src.utils.regex import (
    YOUTUBE_PLAYLIST_SHORTHAND_REGEX,
    YOUTUBE_PLAYLIST_URL,
    YT_CHANNEL,
    YT_CHANNEL_SHORTHAND,
    re_compile,
)

# _CHAR_REPLACEMENTS = load_static_config("character_replacements.json")

_LIGATURE_REPLACEMENTS = {
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
}

_SPECIAL_CHAR_REPLACEMENTS = {
    "@": " at ",
    "&": " and ",
    "+": " plus ",
    "%": " percent ",
    "#": " number ",
    "$": " dollar ",
    "=": " equals ",
    "°": " degrees ",
    "©": "",
    "®": "",
    "™": "",
    "€": " euro ",
    "£": " pound ",
    "¥": " yen ",
    "§": " section ",
    "†": "",
    "‡": "",
    "•": "",
    "…": "",
    "\u201c": '"',
    "\u201d": '"',
    "\u2018": "'",
    "\u2019": "'",
    "–": "-",
    "—": "-",
}

_NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
    "hundred": "100",
    "thousand": "1000",
}

_ROMAN_NUMERALS = {
    "IV": "4",
    "VIII": "8",
    "VII": "7",
    "VI": "6",
    "V": "5",
    "IX": "9",
    "X": "10",
    "III": "3",
    "II": "2",
    "I": "1",
}


def remove_file_extension(filename: str) -> str:
    return re_compile(r"(?i)\.[a-z34]+$").sub("", filename)


@lru_cache(maxsize=1000)
def remove_control_chars(text: str | None) -> str:
    """Remove/escape problematic characters for XML that ElementTree doesn't handle.

    Specifically handles control characters (0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F)
    which are illegal in XML and cause parsing errors.
    """
    if not text:
        return ""
    # Remove control characters except tab (0x09), newline (0x0A), carriage return (0x0D)
    text = re_compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]").sub("", text)
    return text


@lru_cache(maxsize=1000)
def create_slug(title: str) -> str:
    # Convert non-English characters to their nearest English equivalents
    _title = remove_file_extension(title)
    slug = unidecode(_title).lower()

    slug = re_compile(r"([a-z]+)_s\b").sub(r"\1's", slug)  # america_s -> america's
    slug = re_compile(r"\b([a-z]+)'([a-z]{1,2})\b").sub(r"\1\2", slug)  # they'll

    slug = slug.replace(" ", "-").replace("_", "-")
    slug = re_compile(r"[^a-z0-9-]").sub("", slug)
    slug = re_compile(r"-+").sub("-", slug)
    slug = slug.strip("-")

    return slug[:100]


def is_slug(text: str) -> bool:
    """Check if the given text is a valid slug."""
    return re_compile(r"^[a-z0-9]+(-[a-z0-9]+)*$").match(text) is not None


def _apply_roman_numerals(text: str) -> str:
    for roman, num in _ROMAN_NUMERALS.items():
        text = re_compile(rf"(?i)\b{roman}\b").sub(num, text)
    return text


def _apply_special_chars(text: str) -> str:
    for char, replacement in _SPECIAL_CHAR_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    return text


def _apply_number_words(text: str) -> str:
    for word, digit in _NUMBER_WORDS.items():
        text = re_compile(rf"(?i)\b{word}\b").sub(digit, text)
    return text


def _apply_ligatures(text: str) -> str:
    for ligature, replacement in _LIGATURE_REPLACEMENTS.items():
        text = text.replace(ligature, replacement)
    return text


@lru_cache(maxsize=1000)
def normalize_text(text: str) -> str:
    text = remove_file_extension(text)
    text = _apply_ligatures(text)
    text = unidecode(text)
    text = re_compile(r"(?i)\(Pt\.?\s*(I{1,3}|IV|V|\d+)\)").sub(r"part \1", text)
    text = _apply_roman_numerals(text)
    text = _apply_special_chars(text)
    text = _apply_number_words(text)
    text = re_compile(r"(?i)\b(\d+)(?:st|nd|rd|th)\b").sub(r"\1", text)
    text = re_compile(r"[^\w\s]").sub(" ", text)
    text = re_compile(r"\s+").sub(" ", text)
    return text.strip().lower()


def is_youtube_channel(text: str) -> bool:
    """Check if the given text is a YouTube channel URL or handle."""
    return (
        YT_CHANNEL.match(text) is not None
        or YT_CHANNEL_SHORTHAND.match(text) is not None
        or YOUTUBE_PLAYLIST_SHORTHAND_REGEX.match(text) is not None
        or YOUTUBE_PLAYLIST_URL.match(text) is not None
    )
