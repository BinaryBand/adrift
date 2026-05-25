import re
import tempfile
import unittest
from pathlib import Path

from adrift.models import PodcastConfig, SourceFilter
from adrift.services.app_common import _expand_include_targets
from adrift.utils.regex import (
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


def _assert_title_normalization_rules_valid(tc: unittest.TestCase, podcast: PodcastConfig) -> None:
    rules = podcast.cleanup.title_normalization

    for pattern in rules.prefix_patterns + rules.suffix_patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            tc.fail(f"{podcast.name}: invalid title normalization pattern {pattern!r}: {exc}")

    for replacement in rules.replacements:
        try:
            re.compile(replacement.pattern)
        except re.error as exc:
            tc.fail(
                f"{podcast.name}: invalid title normalization replacement pattern "
                f"{replacement.pattern!r}: {exc}"
            )
        tc.assertIn(
            replacement.target,
            {"title", "slug"},
            f"{podcast.name}: invalid title normalization target {replacement.target!r}",
        )


def _assert_schedule_rules_valid(tc: unittest.TestCase, podcast: PodcastConfig) -> None:
    for rule in podcast.schedule:
        tc.assertIsInstance(rule, str)
        tc.assertTrue(
            rule.startswith("FREQ=")
            or (
                "DTSTART:" in rule.upper() and "RRULE:" in rule.upper() and "FREQ=" in rule.upper()
            ),
            f"{podcast.name}: unsupported schedule format {rule!r}",
        )

    for fs in podcast.references + podcast.downloads:
        for rule in fs.filters.r_rules:
            tc.assertIsInstance(rule, str)
            tc.assertTrue(
                rule.startswith("FREQ=")
                or (
                    "DTSTART:" in rule.upper()
                    and "RRULE:" in rule.upper()
                    and "FREQ=" in rule.upper()
                ),
                f"{podcast.name}: invalid r_rules entry {rule!r}",
            )


def _assert_feed_source_valid(tc: unittest.TestCase, podcast: PodcastConfig) -> None:
    for fs in podcast.references:
        tc.assertIsInstance(fs.url, str)
        tc.assertTrue(is_valid_url(fs.url), f"Invalid reference URL: {fs.url}")
        _assert_filter_rules_valid(tc, fs.filters, f"{podcast.name} reference {fs.url} filters")

    for fs in podcast.downloads:
        tc.assertIsInstance(fs.url, str)
        tc.assertTrue(is_valid_url(fs.url), f"Invalid download URL: {fs.url}")
        _assert_filter_rules_valid(tc, fs.filters, f"{podcast.name} download {fs.url} filters")


class AuditConfigs(unittest.TestCase):
    def test_audit_podcast_configs(self):
        """Test that all podcast configs parsed from TOML are structurally valid."""
        from dotenv import find_dotenv

        from adrift.services.app_common import load_config  # type: ignore[attr-defined]

        all_files = Path(find_dotenv()).parent.glob("config/*.toml")
        configs: list[PodcastConfig] = []
        for file in all_files:
            configs.extend(load_config(file.as_posix()))  # type: ignore[name-defined]

        self.assertGreater(len(configs), 0, "No podcast configs found")

        for podcast in configs:
            self.assertIsInstance(podcast, PodcastConfig)
            _assert_title_normalization_rules_valid(self, podcast)
            _assert_feed_source_valid(self, podcast)
            _assert_schedule_rules_valid(self, podcast)


class ExpandIncludeTargets(unittest.TestCase):
    def test_glob_pattern_includes_hidden_toml_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            config_dir.mkdir()
            visible = config_dir / "podcasts.toml"
            hidden = config_dir / ".podcasts.toml"
            visible.write_text("", encoding="utf-8")
            hidden.write_text("", encoding="utf-8")

            expanded = _expand_include_targets([f"{config_dir}/*.toml"])

            self.assertEqual(expanded, [visible.as_posix(), hidden.as_posix()])


if __name__ == "__main__":
    unittest.main()
