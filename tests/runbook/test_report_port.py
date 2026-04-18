from datetime import datetime, timezone
from pathlib import Path

from src.adapters.report import FileReportAdapter
from src.app_common import FeedSource, PodcastConfig
from src.models.metadata import RssEpisode
from src.models.pipeline import MatchCandidateTrace, MergeResult, ReferenceMatchTrace


def _config() -> PodcastConfig:
    return PodcastConfig(
        name="Example Show",
        references=[FeedSource(url="https://example.com/reference.rss")],
        downloads=[FeedSource(url="https://www.youtube.com/@example")],
    )


def _episode(identifier: str, title: str) -> RssEpisode:
    return RssEpisode(
        id=identifier,
        title=title,
        author="Example Author",
        content=f"https://example.com/{identifier}.mp3",
        description=f"Description for {title}",
        pub_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def test_report_adapter_writes_split_report_files(tmp_path: Path) -> None:
    config = _config()
    result = MergeResult(
        config=config,
        references=[_episode("ref-1", "Reference Episode")],
        downloads=[_episode("dl-1", "Download Episode")],
        match_traces=[
            ReferenceMatchTrace(
                reference_index=0,
                matched_download_index=0,
                matched_score=0.91,
                candidates=[
                    MatchCandidateTrace(
                        download_index=0,
                        score=0.91,
                        reason="matched",
                    )
                ],
            )
        ],
        pairs=[(0, 0)],
        episodes=[],
    )

    paths = FileReportAdapter().generate_reports(result, tmp_path)

    assert sorted(path.name for path in paths) == [
        "greedy_matches.md",
        "matches.md",
        "report.md",
    ]
    feeds_dir = tmp_path / config.slug / "feeds"
    assert (feeds_dir / "report.md").exists()
    assert (feeds_dir / "matches.md").exists()
    assert (feeds_dir / "greedy_matches.md").exists()
    assert "# Matches: Example Show" in (feeds_dir / "matches.md").read_text()
    assert "# Greedy Matches: Example Show" in (feeds_dir / "greedy_matches.md").read_text()
