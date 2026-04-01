"""Tests for the FilterRules model and RRULE schedule matching."""

import importlib
import os
import re
import sys
import unittest
from pathlib import Path
from datetime import datetime

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())

# Provide placeholder S3 credentials so importing src.app_common does not
# fail the module-level assertions in src/files/s3.py.  setdefault leaves
# real credentials untouched when running in a fully configured environment.
os.environ.setdefault("S3_USERNAME", "_test")
os.environ.setdefault("S3_SECRET_KEY", "_test")
os.environ.setdefault("S3_ENDPOINT", "http://localhost")
os.environ.setdefault("S3_REGION", "us-east-1")

app_common = importlib.import_module("src.app_common")
SourceFilter = app_common.SourceFilter
_schedule_matches_today = app_common._schedule_matches_today


class TestFilterRulesToRegex(unittest.TestCase):
    """Tests for FilterRules.to_regex()."""

    def test_empty_rules_return_none(self):
        rules = SourceFilter()
        self.assertIsNone(rules.to_regex())

    def test_exclude_only(self):
        rules = SourceFilter(exclude=["bonus", "preview"])
        regex_str = rules.to_regex()
        self.assertIsNotNone(regex_str)
        regex = re.compile(regex_str)  # type: ignore[arg-type]

        self.assertIsNone(regex.search("This is a bonus episode"))
        self.assertIsNone(regex.search("Preview: next week"))
        self.assertIsNotNone(regex.search("Regular Episode 42"))

    def test_include_only(self):
        rules = SourceFilter(include=["Last Week Tonight"])
        regex_str = rules.to_regex()
        self.assertIsNotNone(regex_str)
        regex = re.compile(regex_str)  # type: ignore[arg-type]

        self.assertIsNotNone(regex.search("Last Week Tonight With John Oliver"))
        self.assertIsNone(regex.search("Some Other Show"))

    def test_include_and_exclude(self):
        rules = SourceFilter(
            include=["Stuff You Should Know"],
            exclude=["sysk", "selects:"],
        )
        regex_str = rules.to_regex()
        self.assertIsNotNone(regex_str)
        regex = re.compile(regex_str)  # type: ignore[arg-type]

        self.assertIsNotNone(regex.search("Episode 500 | Stuff You Should Know"))
        self.assertIsNone(regex.search("SYSK Selects: Episode 100"))
        self.assertIsNone(regex.search("Short Stuff: sysk mini"))
        self.assertIsNone(regex.search("Some Unrelated Show"))

    def test_exclude_start_anchored(self):
        """Exclude patterns starting with ^ should only match at string start."""
        rules = SourceFilter(exclude=["^Dateline presents:"])
        regex_str = rules.to_regex()
        self.assertIsNotNone(regex_str)
        regex = re.compile(regex_str)  # type: ignore[arg-type]

        # At the start → excluded
        self.assertIsNone(regex.search("Dateline presents: Mystery"))
        # Not at the start → allowed
        self.assertIsNotNone(regex.search("NBC Dateline presents: Special"))

    def test_case_insensitive_matching(self):
        rules = SourceFilter(exclude=["bonus"])
        regex_str = rules.to_regex()
        self.assertIsNotNone(regex_str)
        regex = re.compile(regex_str)  # type: ignore[arg-type]

        self.assertIsNone(regex.search("BONUS Episode"))
        self.assertIsNone(regex.search("Bonus Content"))
        self.assertIsNotNone(regex.search("Regular Show"))

    def test_to_regex_produces_valid_regex(self):
        """to_regex() output should always be compilable."""
        rules = SourceFilter(
            include=["Stuff You Should Know"],
            exclude=["sysk", "this day in history", "^Dateline presents:"],
        )
        regex_str = rules.to_regex()
        self.assertIsNotNone(regex_str)
        try:
            re.compile(regex_str)  # type: ignore[arg-type]
        except re.error as exc:
            self.fail(f"to_regex() produced invalid regex: {exc}")

    def test_multiple_include_alternatives(self):
        """include acts as an OR – any matching pattern admits the episode."""
        rules = SourceFilter(include=["Episode One", "Episode Two"])
        regex_str = rules.to_regex()
        self.assertIsNotNone(regex_str)
        regex = re.compile(regex_str)  # type: ignore[arg-type]

        self.assertIsNotNone(regex.search("Episode One: The Beginning"))
        self.assertIsNotNone(regex.search("Episode Two: The Sequel"))
        self.assertIsNone(regex.search("Episode Three: The Finale"))


class TestScheduleMatchesToday(unittest.TestCase):
    """Tests for _schedule_matches_today()."""

    def test_byday_matches_today(self):
        """If BYDAY contains today's code the function returns True."""
        result = _schedule_matches_today(
            "FREQ=WEEKLY;BYDAY=WE,FR",
            "Some Show",
            datetime(2026, 4, 1),  # Wednesday
        )
        self.assertTrue(result)

    def test_byday_does_not_match_today(self):
        """If BYDAY does not contain today's code the function returns False."""
        result = _schedule_matches_today(
            "FREQ=WEEKLY;BYDAY=WE,FR",
            "Some Show",
            datetime(2026, 3, 30),  # Monday
        )
        self.assertFalse(result)

    def test_no_byday_uses_rrule_defaults(self):
        """FREQ=WEEKLY without BYDAY is evaluated directly by dateutil RRULE."""
        result = _schedule_matches_today(
            "FREQ=WEEKLY", "Coffeezilla", datetime(2026, 4, 1)
        )
        self.assertTrue(result)

    def test_single_byday(self):
        result = _schedule_matches_today(
            "FREQ=WEEKLY;BYDAY=MO",
            "Alyssa Grenfell",
            datetime(2026, 3, 30),
        )
        self.assertTrue(result)

        result = _schedule_matches_today(
            "FREQ=WEEKLY;BYDAY=MO",
            "Alyssa Grenfell",
            datetime(2026, 3, 31),
        )
        self.assertFalse(result)

    def test_rrule_interval_supported(self):
        """dateutil-backed parser should support additional RRULE fields."""
        result = _schedule_matches_today(
            "FREQ=DAILY;INTERVAL=2",
            "Any Show",
            datetime(2026, 4, 1),
        )
        self.assertTrue(result)

    def test_dtstart_plus_rrule_supported(self):
        """RFC5545 DTSTART+RRULE strings should evaluate schedule windows."""
        schedule = "DTSTART:20240124T000000Z\nRRULE:FREQ=WEEKLY;BYDAY=MO"
        self.assertTrue(_schedule_matches_today(schedule, "The Daily Show", datetime(2026, 3, 30)))
        self.assertFalse(_schedule_matches_today(schedule, "The Daily Show", datetime(2026, 3, 31)))


if __name__ == "__main__":
    unittest.main()
