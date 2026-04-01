import unittest
import re
from pathlib import Path
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.app_common import SourceFilter, PodcastConfig
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


def _assert_filter_rules_valid(
    tc: unittest.TestCase, rules: SourceFilter, label: str
) -> None:
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
        from src.app_common import _load_config

        configs: list[PodcastConfig] = []
        for name in ("podcasts", "youtube"):
            configs.extend(_load_config(name))

        self.assertGreater(len(configs), 0, "No podcast configs found")

        for podcast in configs:
            self.assertIsInstance(podcast, PodcastConfig)

            for fs in podcast.references:
                self.assertIsInstance(fs.url, str)
                self.assertTrue(
                    is_valid_url(fs.url), f"Invalid reference URL: {fs.url}"
                )

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

            # Validate schedule is a list of FREQ= strings when present
            for rule in podcast.schedule:
                self.assertIsInstance(rule, str)
                self.assertTrue(
                    rule.startswith("FREQ="),
                    f"{podcast.name}: schedule rule should start with FREQ=, got {rule!r}",
                )


if __name__ == "__main__":
    unittest.main()
