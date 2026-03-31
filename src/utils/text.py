from unidecode import unidecode
from functools import lru_cache
from pathlib import Path
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
# from src.app_common import load_static_config
from src.utils.regex import (
    YT_CHANNEL,
    YT_CHANNEL_SHORTHAND,
    re_compile,
)


# _CHAR_REPLACEMENTS = load_static_config("character_replacements.json")


_CHAR_REPLACEMENTS = {
    "accented_characters": {
        "á": "a",
        "à": "a",
        "ä": "a",
        "â": "a",
        "ā": "a",
        "ã": "a",
        "é": "e",
        "è": "e",
        "ë": "e",
        "ê": "e",
        "ē": "e",
        "í": "i",
        "ì": "i",
        "ï": "i",
        "î": "i",
        "ī": "i",
        "ó": "o",
        "ò": "o",
        "ö": "o",
        "ô": "o",
        "ō": "o",
        "õ": "o",
        "ú": "u",
        "ù": "u",
        "ü": "u",
        "û": "u",
        "ū": "u",
        "ç": "c",
        "ñ": "n",
        "ß": "ss",
        "Á": "A",
        "À": "A",
        "Ä": "A",
        "Â": "A",
        "Ā": "A",
        "Ã": "A",
        "É": "E",
        "È": "E",
        "Ë": "E",
        "Ê": "E",
        "Ē": "E",
        "Í": "I",
        "Ì": "I",
        "Ï": "I",
        "Î": "I",
        "Ī": "I",
        "Ó": "O",
        "Ò": "O",
        "Ö": "O",
        "Ô": "O",
        "Ō": "O",
        "Õ": "O",
        "Ú": "U",
        "Ù": "U",
        "Ü": "U",
        "Û": "U",
        "Ū": "U",
        "Ç": "C",
        "Ñ": "N",
    },
    "special_characters": {
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
    },
    "number_words": {
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
    },
    "roman_numerals": {
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
    },
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


@lru_cache(maxsize=1000)
def normalize_text(text: str) -> str:
    text = remove_file_extension(text)
    text = unidecode(text)

    # (Pt. II) -> part II
    text = re_compile(r"(?i)\(Pt\.?\s*(I{1,3}|IV|V|\d+)\)").sub(r"part \1", text)

    # Convert Roman numerals to numbers using config
    roman_numerals = _CHAR_REPLACEMENTS.get("roman_numerals", {})
    for roman, num in roman_numerals.items():
        text = re_compile(rf"(?i)\b{roman}\b").sub(num, text)

    # Normalize special characters using config
    special_chars = _CHAR_REPLACEMENTS.get("special_characters", {})
    for char, replacement in special_chars.items():
        text = text.replace(char, replacement)

    # Normalize numbers using config
    number_words = _CHAR_REPLACEMENTS.get("number_words", {})
    for word, digit in number_words.items():
        text = re_compile(rf"(?i)\b{word}\b").sub(digit, text)

    text = re_compile(r"(?i)\b(\d+)(?:st|nd|rd|th)\b").sub(r"\1", text)  # 1st -> 1
    text = re_compile(r"[^\w\s]").sub(" ", text)  # Remove punctuation
    text = re_compile(r"\s+").sub(" ", text)  # Normalize whitespace

    return text.strip().lower()


def is_youtube_channel(text: str) -> bool:
    """Check if the given text is a YouTube channel URL or handle."""
    return (
        YT_CHANNEL.match(text) is not None
        or YT_CHANNEL_SHORTHAND.match(text) is not None
    )
