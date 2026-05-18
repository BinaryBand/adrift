"""Tests for src.utils.image — feedparser and yt-dlp image URL extraction."""

import unittest

from adrift.models import YtDlpImage
from adrift.utils.image import (
    extract_image_from_feedparser,
    extract_image_from_ytdlp,
    extract_image_from_ytdlp_list,
)


class _AttrObj:
    """Minimal object exposing arbitrary attributes for testing."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestExtractImageFromFeedparser(unittest.TestCase):
    def test_plain_string(self):
        self.assertEqual(
            extract_image_from_feedparser("https://img.example.com/cover.jpg"),
            "https://img.example.com/cover.jpg",
        )

    def test_empty_string_returns_empty(self):
        self.assertEqual(extract_image_from_feedparser(""), "")

    def test_none_returns_empty(self):
        self.assertEqual(extract_image_from_feedparser(None), "")

    def test_dict_with_href(self):
        self.assertEqual(
            extract_image_from_feedparser({"href": "https://img.example.com/a.jpg"}),
            "https://img.example.com/a.jpg",
        )

    def test_dict_with_url(self):
        self.assertEqual(
            extract_image_from_feedparser({"url": "https://img.example.com/b.jpg"}),
            "https://img.example.com/b.jpg",
        )

    def test_dict_prefers_href_over_url(self):
        result = extract_image_from_feedparser(
            {"href": "https://href.example.com/", "url": "https://url.example.com/"}
        )
        self.assertEqual(result, "https://href.example.com/")

    def test_dict_with_no_image_keys_returns_empty(self):
        self.assertEqual(extract_image_from_feedparser({"title": "foo"}), "")

    def test_object_with_href_attr(self):
        obj = _AttrObj(href="https://attr-href.example.com/img.jpg")
        self.assertEqual(
            extract_image_from_feedparser(obj), "https://attr-href.example.com/img.jpg"
        )

    def test_object_with_url_attr(self):
        obj = _AttrObj(url="https://attr-url.example.com/img.jpg")
        self.assertEqual(extract_image_from_feedparser(obj), "https://attr-url.example.com/img.jpg")

    def test_integer_returns_empty(self):
        self.assertEqual(extract_image_from_feedparser(42), "")


class TestExtractImageFromYtdlp(unittest.TestCase):
    def test_ytdlp_image_model(self):
        img = YtDlpImage(url="https://yt.example.com/thumb.jpg", width=1280, height=720)
        self.assertEqual(extract_image_from_ytdlp(img), "https://yt.example.com/thumb.jpg")

    def test_ytdlp_image_model_none_url(self):
        img = YtDlpImage(url=None)
        self.assertEqual(extract_image_from_ytdlp(img), "")

    def test_raw_dict_with_url(self):
        self.assertEqual(
            extract_image_from_ytdlp({"url": "https://dict.example.com/t.jpg"}),
            "https://dict.example.com/t.jpg",
        )

    def test_raw_dict_without_url_returns_empty(self):
        self.assertEqual(extract_image_from_ytdlp({"width": 120}), "")

    def test_none_returns_empty(self):
        self.assertEqual(extract_image_from_ytdlp(None), "")

    def test_string_returns_empty(self):
        self.assertEqual(extract_image_from_ytdlp("https://string.example.com/"), "")


class TestExtractImageFromYtdlpList(unittest.TestCase):
    def test_empty_list_returns_empty(self):
        self.assertEqual(extract_image_from_ytdlp_list([]), "")

    def test_single_entry_returns_its_url(self):
        img = YtDlpImage(url="https://single.example.com/img.jpg")
        self.assertEqual(extract_image_from_ytdlp_list([img]), "https://single.example.com/img.jpg")

    def test_returns_last_entry(self):
        imgs = [
            YtDlpImage(url="https://first.example.com/"),
            YtDlpImage(url="https://last.example.com/"),
        ]
        self.assertEqual(extract_image_from_ytdlp_list(imgs), "https://last.example.com/")

    def test_list_of_dicts(self):
        data = [{"url": "https://first.example.com/"}, {"url": "https://last.example.com/"}]
        self.assertEqual(extract_image_from_ytdlp_list(data), "https://last.example.com/")


if __name__ == "__main__":
    unittest.main()
