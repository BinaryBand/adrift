"""Tests for the FilterRules model and RRULE schedule matching."""

import importlib
import re
import unittest
from datetime import UTC, datetime

app_common = importlib.import_module("adrift.core.services.app_common")
SourceFilter = app_common.SourceFilter
_schedule_matches_today = app_common._schedule_matches_today


class TestFilterRulesToRegex(unittest.TestCase):
    """Tests for FilterRules.to_regex()."""

    def test_empty_rules_return_none(self):
        rules = SourceFilter()
        assert rules.to_regex() is None

    def test_exclude_only(self):
        rules = SourceFilter(exclude=["bonus", "preview"])
        regex_str = rules.to_regex()
        assert regex_str is not None
        regex = re.compile(regex_str)  # type: ignore[arg-type]

        assert regex.search("This is a bonus episode") is None
        assert regex.search("Preview: next week") is None
        assert regex.search("Regular Episode 42") is not None

    def test_include_only(self):
        rules = SourceFilter(include=["Last Week Tonight"])
        regex_str = rules.to_regex()
        assert regex_str is not None
        regex = re.compile(regex_str)  # type: ignore[arg-type]

        assert regex.search("Last Week Tonight With John Oliver") is not None
        assert regex.search("Some Other Show") is None

    def test_include_and_exclude(self):
        rules = SourceFilter(
            include=["Stuff You Should Know"],
            exclude=["sysk", "selects:"],
        )
        regex_str = rules.to_regex()
        assert regex_str is not None
        regex = re.compile(regex_str)  # type: ignore[arg-type]

        assert regex.search("Episode 500 | Stuff You Should Know") is not None
        assert regex.search("SYSK Selects: Episode 100") is None
        assert regex.search("Short Stuff: sysk mini") is None
        assert regex.search("Some Unrelated Show") is None

    def test_exclude_start_anchored(self):
        """Exclude patterns starting with ^ should only match at string start."""
        rules = SourceFilter(exclude=["^Dateline presents:"])
        regex_str = rules.to_regex()
        assert regex_str is not None
        regex = re.compile(regex_str)  # type: ignore[arg-type]

        # At the start → excluded
        assert regex.search("Dateline presents: Mystery") is None
        # Not at the start → allowed
        assert regex.search("NBC Dateline presents: Special") is not None

    def test_case_insensitive_matching(self):
        rules = SourceFilter(exclude=["bonus"])
        regex_str = rules.to_regex()
        assert regex_str is not None
        regex = re.compile(regex_str)  # type: ignore[arg-type]

        assert regex.search("BONUS Episode") is None
        assert regex.search("Bonus Content") is None
        assert regex.search("Regular Show") is not None

    def test_to_regex_produces_valid_regex(self):
        """to_regex() output should always be compilable."""
        rules = SourceFilter(
            include=["Stuff You Should Know"],
            exclude=["sysk", "this day in history", "^Dateline presents:"],
        )
        regex_str = rules.to_regex()
        assert regex_str is not None
        try:
            re.compile(regex_str)  # type: ignore[arg-type]
        except re.error as exc:
            self.fail(f"to_regex() produced invalid regex: {exc}")

    def test_multiple_include_alternatives(self):
        """include acts as an OR - any matching pattern admits the episode."""
        rules = SourceFilter(include=["Episode One", "Episode Two"])
        regex_str = rules.to_regex()
        assert regex_str is not None
        regex = re.compile(regex_str)  # type: ignore[arg-type]

        assert regex.search("Episode One: The Beginning") is not None
        assert regex.search("Episode Two: The Sequel") is not None
        assert regex.search("Episode Three: The Finale") is None


class TestScheduleMatchesToday(unittest.TestCase):
    """Tests for _schedule_matches_today()."""

    def test_byday_matches_today(self):
        """If BYDAY contains today's code the function returns True."""
        result = _schedule_matches_today(
            "FREQ=WEEKLY;BYDAY=WE,FR",
            "Some Show",
            datetime(2026, 4, 1, tzinfo=UTC),  # Wednesday
        )
        assert result

    def test_byday_does_not_match_today(self):
        """If BYDAY does not contain today's code the function returns False."""
        result = _schedule_matches_today(
            "FREQ=WEEKLY;BYDAY=WE,FR",
            "Some Show",
            datetime(2026, 3, 30, tzinfo=UTC),  # Monday
        )
        assert not result

    def test_no_byday_uses_rrule_defaults(self):
        """FREQ=WEEKLY without BYDAY is evaluated directly by dateutil RRULE."""
        result = _schedule_matches_today(
            "FREQ=WEEKLY", "Coffeezilla", datetime(2026, 4, 1, tzinfo=UTC)
        )
        assert result

    def test_single_byday(self):
        result = _schedule_matches_today(
            "FREQ=WEEKLY;BYDAY=MO",
            "Alyssa Grenfell",
            datetime(2026, 3, 30, tzinfo=UTC),
        )
        assert result

        result = _schedule_matches_today(
            "FREQ=WEEKLY;BYDAY=MO",
            "Alyssa Grenfell",
            datetime(2026, 3, 31, tzinfo=UTC),
        )
        assert not result

    def test_rrule_interval_supported(self):
        """dateutil-backed parser should support additional RRULE fields."""
        result = _schedule_matches_today(
            "FREQ=DAILY;INTERVAL=2",
            "Any Show",
            datetime(2026, 4, 1, tzinfo=UTC),
        )
        assert result

    def test_dtstart_plus_rrule_supported(self):
        """RFC5545 DTSTART+RRULE strings should evaluate schedule windows."""
        schedule = "DTSTART:20240124T000000Z\nRRULE:FREQ=WEEKLY;BYDAY=MO"
        assert _schedule_matches_today(
            schedule, "The Daily Show", datetime(2026, 3, 30, tzinfo=UTC)
        )
        assert not _schedule_matches_today(
            schedule, "The Daily Show", datetime(2026, 3, 31, tzinfo=UTC)
        )


class TestSourceFilterRRules(unittest.TestCase):
    """Tests for SourceFilter.r_rules field."""

    def test_r_rules_field_accepts_rrule_strings(self):
        """r_rules accepts a list of RFC 5545 RRULE strings."""
        f = SourceFilter(r_rules=["FREQ=WEEKLY;BYDAY=MO"])
        assert f.r_rules == ["FREQ=WEEKLY;BYDAY=MO"]

    def test_r_rules_empty_by_default(self):
        """r_rules defaults to empty list."""
        f = SourceFilter()
        assert f.r_rules == []

    def test_r_rules_multiple_entries(self):
        """r_rules accepts multiple RRULE strings."""
        f = SourceFilter(r_rules=["FREQ=WEEKLY;BYDAY=MO", "FREQ=WEEKLY;BYDAY=WE"])
        assert len(f.r_rules) == 2


if __name__ == "__main__":
    unittest.main()
