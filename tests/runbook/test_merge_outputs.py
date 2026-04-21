import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from runbook import merge as merge_mod
from src.models.metadata import RssEpisode
from src.models.output import EpisodeData
from src.models.pipeline import MergeResult
from src.models.podcast_config import FeedSource, PodcastConfig


def _config() -> PodcastConfig:
    return PodcastConfig(
        name="Example Show",
        path="/tmp/example-show",
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
    assert (series_dir / "feeds" / "combined.json").exists()
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "index.json").exists()

    combined = json.loads((series_dir / "feeds" / "combined.json").read_text())
    # Expect the combined file to contain the full MergeResult payload
    assert combined["config"]["name"] == config.name
    assert len(combined.get("episodes", [])) == 1
    assert combined["episodes"][0]["id"] == "merged-1"

    index_payload = json.loads((tmp_path / "index.json").read_text())
    assert index_payload["series"][0]["slug"] == config.slug
    assert set(index_payload["series"][0]["feeds"].keys()) == {"combined"}
    assert index_payload["series"][0]["feeds"]["combined"] == f"{config.slug}/feeds/combined.json"


def test_main_writes_bundle_and_stdout(tmp_path: Path, capsys) -> None:
    config = _config()
    references = [_rss_episode("ref-1", "Reference Episode", "https://example.com/reference-1.mp3")]
    downloads = [_rss_episode("dl-1", "Download Episode", "https://youtube.com/watch?v=abc123")]
    merged = [_merged_episode()]
    result = MergeResult(
        config=config,
        references=references,
        downloads=downloads,
        pairs=[(0, 0)],
        episodes=merged,
    )

    argv = [
        "adrift-merge",
        "--include",
        "config/youtube.toml",
        "--output-dir",
        tmp_path.as_posix(),
        "--include-counts",
        "--refresh-sources",
    ]

    with (
        patch("src.app_common.load_podcasts_config", return_value=[config]),
        patch("src.catalog.merge_config", return_value=result) as mock_merge_config,
        patch.object(sys, "argv", argv),
    ):
        merge_mod.main()

    stdout_payload = json.loads(capsys.readouterr().out)
    assert stdout_payload[0]["name"] == config.name
    assert stdout_payload[0]["references_count"] == 1
    assert stdout_payload[0]["downloads_count"] == 1
    assert (tmp_path / config.slug / "feeds" / "combined.json").exists()
    assert (tmp_path / config.slug / "feeds" / "report.md").exists()
    assert (tmp_path / config.slug / "feeds" / "matches.md").exists()
    assert (tmp_path / config.slug / "feeds" / "greedy_matches.md").exists()
    call = mock_merge_config.call_args
    assert call.args[0] == config
    assert call.kwargs["refresh_sources"] is True
    assert callable(call.kwargs.get("on_stage"))


def test_main_updates_output_file_after_each_podcast(tmp_path: Path, capsys) -> None:
    first = PodcastConfig(
        name="First Show",
        path="/tmp/first-show",
        references=[FeedSource(url="https://example.com/first-reference.rss")],
        downloads=[FeedSource(url="yt://@first-show")],
    )
    second = PodcastConfig(
        name="Second Show",
        path="/tmp/second-show",
        references=[FeedSource(url="https://example.com/second-reference.rss")],
        downloads=[FeedSource(url="yt://@second-show")],
    )
    first_result = MergeResult(
        config=first,
        references=[_rss_episode("ref-1", "First Ref", "https://example.com/first-ref.mp3")],
        downloads=[_rss_episode("dl-1", "First Dl", "https://youtube.com/watch?v=first")],
        pairs=[(0, 0)],
        episodes=[_merged_episode()],
    )
    second_result = MergeResult(
        config=second,
        references=[_rss_episode("ref-2", "Second Ref", "https://example.com/second-ref.mp3")],
        downloads=[_rss_episode("dl-2", "Second Dl", "https://youtube.com/watch?v=second")],
        pairs=[(0, 0)],
        episodes=[
            EpisodeData(
                id="merged-2",
                title="Merged Episode 2",
                description="Merged description 2",
                source=[
                    "https://example.com/second-reference-1.mp3",
                    "https://youtube.com/watch?v=second",
                ],
                upload_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
            )
        ],
    )
    output_file = tmp_path / "merge-report.json"
    snapshots: list[list[dict[str, object]]] = []

    def _capture_report(path: Path, payload: object) -> None:
        if path == output_file:
            snapshots.append(json.loads(json.dumps(payload)))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    argv = [
        "adrift-merge",
        "--include",
        "config/youtube.toml",
        "--output-dir",
        (tmp_path / "bundles").as_posix(),
        "--output-file",
        output_file.as_posix(),
    ]

    with (
        patch("src.app_common.load_podcasts_config", return_value=[first, second]),
        patch("src.catalog.merge_config", side_effect=[first_result, second_result]),
        patch.object(merge_mod, "_write_json", side_effect=_capture_report),
        patch.object(sys, "argv", argv),
    ):
        merge_mod.main()

    stdout_payload = json.loads(capsys.readouterr().out)
    assert len(stdout_payload) == 2
    assert len(snapshots) == 2
    assert [entry["name"] for entry in snapshots[0]] == ["First Show"]
    assert [entry["name"] for entry in snapshots[1]] == ["First Show", "Second Show"]
    file_payload = json.loads(output_file.read_text())
    assert [entry["name"] for entry in file_payload] == ["First Show", "Second Show"]


def test_main_defaults_output_dir_to_downloads(tmp_path: Path, capsys) -> None:
    config = _config()
    downloads_root = tmp_path / "downloads"
    result = MergeResult(
        config=config,
        references=[_rss_episode("ref-1", "Reference Episode", "https://example.com/ref.mp3")],
        downloads=[_rss_episode("dl-1", "Download Episode", "https://youtube.com/watch?v=abc123")],
        pairs=[(0, 0)],
        episodes=[_merged_episode()],
    )

    argv = [
        "adrift-merge",
        "--include",
        "config/youtube.toml",
    ]

    with (
        patch("src.app_common.load_podcasts_config", return_value=[config]),
        patch("src.catalog.merge_config", return_value=result),
        patch.object(merge_mod, "DEFAULT_OUTPUT_DIR", downloads_root.as_posix()),
        patch.object(sys, "argv", argv),
    ):
        merge_mod.main()

    capsys.readouterr()
    assert (downloads_root / config.slug / "feeds" / "combined.json").exists()
    assert (downloads_root / "report.json").exists()
    assert (downloads_root / "index.json").exists()


def test_main_emits_timings_to_stderr(tmp_path: Path, capsys) -> None:
    config = _config()
    result = MergeResult(
        config=config,
        references=[_rss_episode("ref-1", "Reference Episode", "https://example.com/ref.mp3")],
        downloads=[_rss_episode("dl-1", "Download Episode", "https://youtube.com/watch?v=abc123")],
        pairs=[(0, 0)],
        episodes=[_merged_episode()],
    )

    def _merge_config_with_timings(*args, **kwargs) -> MergeResult:
        timings = kwargs.get("timings")
        if isinstance(timings, dict):
            timings.update(
                {
                    "process_feeds": 0.01,
                    "process_sources": 0.02,
                    "align_episodes": 0.03,
                    "merge_episodes": 0.004,
                    "merge_config_total": 0.064,
                }
            )
        return result

    argv = [
        "adrift-merge",
        "--include",
        "config/youtube.toml",
        "--output-dir",
        tmp_path.as_posix(),
        "--timings",
    ]

    with (
        patch("src.app_common.load_podcasts_config", return_value=[config]),
        patch("src.catalog.merge_config", side_effect=_merge_config_with_timings),
        patch.object(sys, "argv", argv),
    ):
        merge_mod.main()

    captured = capsys.readouterr()
    assert "TIMING load_configs:" in captured.err
    assert f"TIMING {config.name}:" in captured.err
    assert "process_feeds=10.0ms" in captured.err
    assert "align_episodes=30.0ms" in captured.err
    assert "podcast_total=" in captured.err
