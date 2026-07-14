"""Tests for src.utils.media — parse_duration and AUDIO_EXTENSIONS."""

import logging
import unittest

from adrift.core.util.media import AUDIO_EXTENSIONS, parse_duration


class TestParseDuration(unittest.TestCase):
    def test_none_returns_none(self):
        assert parse_duration(None) is None

    def test_empty_string_returns_none(self):
        assert parse_duration("") is None

    def test_seconds_only(self):
        self.assertAlmostEqual(parse_duration("30"), 30.0)

    def test_minutes_and_seconds(self):
        self.assertAlmostEqual(parse_duration("1:30"), 90.0)

    def test_hours_minutes_seconds(self):
        self.assertAlmostEqual(parse_duration("1:30:00"), 5400.0)

    def test_fractional_seconds(self):
        self.assertAlmostEqual(parse_duration("0:01:30.5"), 90.5)

    def test_zero_duration(self):
        self.assertAlmostEqual(parse_duration("0:00"), 0.0)

    def test_unrecognised_format_returns_none_and_warns(self):
        with self.assertLogs("adrift.core.util.media", level=logging.WARNING) as ctx:
            result = parse_duration("1:02:03:04")
        assert result is None
        assert any("1:02:03:04" in line for line in ctx.output)


class TestAudioExtensions(unittest.TestCase):
    def test_is_a_set(self):
        assert isinstance(AUDIO_EXTENSIONS, set)

    def test_contains_expected_formats(self):
        for ext in (".mp3", ".m4a", ".opus", ".ogg", ".flac"):
            assert ext in AUDIO_EXTENSIONS

    def test_extensions_start_with_dot(self):
        for ext in AUDIO_EXTENSIONS:
            assert ext.startswith("."), f"Expected leading dot: {ext!r}"


if __name__ == "__main__":
    unittest.main()
