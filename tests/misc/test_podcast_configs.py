import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.app_common import PodcastConfig, SourceFilter
from src.utils.regex import (
    LINK_REGEX,
    YOUTUBE_PLAYLIST_SHORTHAND_REGEX,
    YT_CHANNEL_SHORTHAND,
)


def is_valid_url(url: str) -> bool:
    """Check if the given URL is valid using LINK_REGEX."""
    return (
        LINK_REGEX.match(url) is not None
        or YT_CHANNEL_SHORTHAND.match(url) is not None
        or YOUTUBE_PLAYLIST_SHORTHAND_REGEX.match(url) is not None
    )


def _assert_filter_rules_valid(tc: unittest.TestCase, rules: SourceFilter, label: str) -> None:
    """Validate a SourceFilter instance: patterns must compile and to_regex() must compile."""
    for pattern in rules.include + rules.exclude:
        try:
            re.compile(pattern)
        except re.error as exc:
            tc.fail(f"{label}: invalid regex pattern {pattern!r}: {exc}")

    generated = rules.to_regex()
    if generated is not None:
        try:
            re.compile(generated)
        except re.error as exc:
            tc.fail(f"{label}: to_regex() produced invalid regex: {exc}")


class AuditConfigs(unittest.TestCase):
    def test_audit_podcast_configs(self):
        """Test that all podcast configs parsed from TOML are structurally valid."""
        # load_podcasts_config filters by today's schedule, but we want to audit
        # all entries regardless of day – load from both files without filtering.
        from dotenv import find_dotenv

        from src.app_common import _load_config

        all_files = Path(find_dotenv()).parent.glob("config/*.toml")
        configs: list[PodcastConfig] = []
        for file in all_files:
            configs.extend(_load_config(file.as_posix()))

        self.assertGreater(len(configs), 0, "No podcast configs found")

        for podcast in configs:
            self.assertIsInstance(podcast, PodcastConfig)

            for fs in podcast.references:
                self.assertIsInstance(fs.url, str)
                self.assertTrue(is_valid_url(fs.url), f"Invalid reference URL: {fs.url}")

            for fs in podcast.downloads:
                self.assertIsInstance(fs.url, str)
                self.assertTrue(is_valid_url(fs.url), f"Invalid download URL: {fs.url}")

            # Validate filter rules for each FeedSource
            for fs in podcast.references:
                _assert_filter_rules_valid(
                    self, fs.filters, f"{podcast.name} reference {fs.url} filters"
                )
            for fs in podcast.downloads:
                _assert_filter_rules_valid(
                    self, fs.filters, f"{podcast.name} download {fs.url} filters"
                )

            # Validate schedule is either legacy FREQ= or RFC5545 DTSTART+RRULE.
            for rule in podcast.schedule:
                self.assertIsInstance(rule, str)
                self.assertTrue(
                    rule.startswith("FREQ=")
                    or (
                        "DTSTART:" in rule.upper()
                        and "RRULE:" in rule.upper()
                        and "FREQ=" in rule.upper()
                    ),
                    f"{podcast.name}: unsupported schedule format {rule!r}",
                )

            # Validate r_rules entries are RRULE strings.
            for fs in podcast.references + podcast.downloads:
                for rule in fs.filters.r_rules:
                    self.assertIsInstance(rule, str)
                    self.assertTrue(
                        rule.startswith("FREQ=")
                        or (
                            "DTSTART:" in rule.upper()
                            and "RRULE:" in rule.upper()
                            and "FREQ=" in rule.upper()
                        ),
                        f"{podcast.name}: invalid r_rules entry {rule!r}",
                    )


if __name__ == "__main__":
    unittest.main()
