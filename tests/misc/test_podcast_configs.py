import unittest
import re
from pathlib import Path
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.app_common import FilterRules, PodcastData, load_podcasts_config
from src.utils.regex import (
    LINK_REGEX,
    YT_CHANNEL_SHORTHAND,
    YOUTUBE_PLAYLIST_SHORTHAND_REGEX,
)


def is_valid_url(url: str) -> bool:
    """Check if the given URL is valid using LINK_REGEX."""
    return (
        LINK_REGEX.match(url) is not None
        or YT_CHANNEL_SHORTHAND.match(url) is not None
        or YOUTUBE_PLAYLIST_SHORTHAND_REGEX.match(url) is not None
    )


def _assert_filter_rules_valid(tc: unittest.TestCase, rules: FilterRules, label: str) -> None:
    """Validate a FilterRules instance: patterns must compile and to_regex() must compile."""
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
        from src.app_common import _load_config

        configs: list[PodcastData] = []
        for name in ("podcasts", "youtube"):
            configs.extend(_load_config(name))

        self.assertGreater(len(configs), 0, "No podcast configs found")

        for podcast in configs:
            self.assertIsInstance(podcast, PodcastData)

            for feed in podcast.feeds:
                self.assertIsInstance(feed, str)
                self.assertTrue(is_valid_url(feed), f"Invalid feed URL: {feed}")

            for source in podcast.sources:
                self.assertIsInstance(source, str)
                self.assertTrue(
                    is_valid_url(source), f"Invalid source URL: {source}"
                )

            # Validate filter rules for each filter set present
            _assert_filter_rules_valid(
                self, podcast.filters, f"{podcast.title} filters"
            )
            if podcast.feed_filters is not None:
                _assert_filter_rules_valid(
                    self, podcast.feed_filters, f"{podcast.title} feed_filters"
                )
            if podcast.source_filters is not None:
                _assert_filter_rules_valid(
                    self, podcast.source_filters, f"{podcast.title} source_filters"
                )

            # Validate schedule is a non-empty string when present
            if podcast.schedule is not None:
                self.assertIsInstance(podcast.schedule, str)
                self.assertTrue(
                    podcast.schedule.startswith("FREQ="),
                    f"{podcast.title}: schedule should start with FREQ=, got {podcast.schedule!r}",
                )


if __name__ == "__main__":
    unittest.main()
