import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from runbook import merge as merge_mod
from src.app_common import FeedSource, PodcastConfig
from src.models.metadata import RssEpisode
from src.models.output import EpisodeData
from src.models.pipeline import MergeResult


def _config() -> PodcastConfig:
    return PodcastConfig(
        name="Example Show",
        references=[FeedSource(url="https://example.com/reference.rss")],
        downloads=[FeedSource(url="yt://@example-show")],
    )


def _rss_episode(identifier: str, title: str, content: str) -> RssEpisode:
    return RssEpisode(
        id=identifier,
        title=title,
        author="Example Author",
        content=content,
        description=f"Description for {title}",
        pub_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _merged_episode() -> EpisodeData:
    return EpisodeData(
        id="merged-1",
        title="Merged Episode",
        description="Merged description",
        source=["https://example.com/reference-1.mp3", "https://youtube.com/watch?v=abc123"],
        upload_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def test_write_series_outputs_creates_expected_layout(tmp_path: Path) -> None:
    config = _config()
    references = [_rss_episode("ref-1", "Reference Episode", "https://example.com/reference-1.mp3")]
    downloads = [_rss_episode("dl-1", "Download Episode", "https://youtube.com/watch?v=abc123")]
    merged = [_merged_episode()]

    result = MergeResult(
        config=config, references=references, downloads=downloads, pairs=[], episodes=merged
    )
    series_entry = merge_mod._write_series_outputs(tmp_path, result)
    merge_mod._write_output_bundle(
        tmp_path.as_posix(),
        [{"name": config.name, "episodes": []}],
        [series_entry],
    )

    series_dir = tmp_path / config.slug
    assert (series_dir / "config.json").exists()
    assert (series_dir / "feeds" / "references.json").exists()
    assert (series_dir / "feeds" / "downloads.json").exists()
    assert (series_dir / "feeds" / "combined.json").exists()
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "index.json").exists()

    combined = json.loads((series_dir / "feeds" / "combined.json").read_text())
    assert combined["kind"] == "combined"
    assert combined["name"] == config.name
    assert combined["episode_count"] == 1
    assert combined["episodes"][0]["id"] == "merged-1"

    index_payload = json.loads((tmp_path / "index.json").read_text())
    assert index_payload["series"][0]["slug"] == config.slug
    assert index_payload["series"][0]["feeds"]["combined"] == f"{config.slug}/feeds/combined.json"


def test_main_writes_bundle_and_stdout(tmp_path: Path, capsys) -> None:
    config = _config()
    references = [
        _rss_episode("ref-1", "Reference Episode", "https://example.com/reference-1.mp3")
    ]
    downloads = [
        _rss_episode("dl-1", "Download Episode", "https://youtube.com/watch?v=abc123")
    ]
    merged = [_merged_episode()]

    argv = [
        "adrift-merge",
        "--include",
        "config/youtube.toml",
        "--output-dir",
        tmp_path.as_posix(),
        "--include-counts",
    ]

    with (
        patch("src.app_common.load_podcasts_config", return_value=[config]),
        patch("src.catalog.process_feeds", return_value=references),
        patch("src.catalog.process_sources", return_value=downloads),
        patch("src.catalog.merge_episode_pairs", return_value=merged),
        patch.object(sys, "argv", argv),
    ):
        merge_mod.main()

    stdout_payload = json.loads(capsys.readouterr().out)
    assert stdout_payload[0]["name"] == config.name
    assert stdout_payload[0]["references_count"] == 1
    assert stdout_payload[0]["downloads_count"] == 1
    assert (tmp_path / config.slug / "feeds" / "combined.json").exists()