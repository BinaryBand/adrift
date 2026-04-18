from datetime import datetime, timezone

from src.adapters.report_sections.match_debug import render_greedy_matches, render_matches
from src.app_common import FeedSource, PodcastConfig
from src.catalog import _build_match_traces
from src.models.metadata import RssEpisode
from src.models.pipeline import MergeResult


def _episode(identifier: str, title: str, day: int) -> RssEpisode:
    return RssEpisode(
        id=identifier,
        title=title,
        author="Author",
        content=f"https://example.com/{identifier}.mp3",
        description=f"Description for {title}",
        pub_date=datetime(2024, 1, day, tzinfo=timezone.utc),
    )


def _config() -> PodcastConfig:
    return PodcastConfig(
        name="Debug Show",
        references=[FeedSource(url="https://example.com/reference.rss")],
        downloads=[FeedSource(url="https://www.youtube.com/@debug-show")],
    )


def test_build_match_traces_records_below_threshold_candidate() -> None:
    references = [_episode("ref-1", "Weekly Briefing 10", 10)]
    downloads = [_episode("dl-1", "Cooking Club 77", 11)]

    traces = _build_match_traces(references, downloads, [], "Debug Show")

    assert len(traces) == 1
    assert traces[0].matched_download_index is None
    assert len(traces[0].candidates) == 1
    assert traces[0].candidates[0].reason == "below_threshold"


def test_render_matches_lists_only_final_assignments() -> None:
    config = _config()
    references = [
        _episode("ref-1", "Budget Breakdown 101", 1),
        _episode("ref-2", "Missing Episode 202", 2),
    ]
    downloads = [
        _episode("dl-1", "Budget Breakdown 101", 1),
        _episode("dl-2", "Another Show Episode", 2),
    ]
    pairs = [(0, 0)]
    match_traces = _build_match_traces(references, downloads, pairs, config.name)
    result = MergeResult(
        config=config,
        references=references,
        downloads=downloads,
        match_traces=match_traces,
        pairs=pairs,
        episodes=[],
    )

    content = render_matches(result)

    assert "# Matches: Debug Show" in content
    assert "Budget Breakdown 101" in content
    assert "Missing Episode 202" in content
    assert "| 2. Missing Episode 202 | Unmatched | — | — |" in content


def test_render_greedy_matches_lists_unmatched_candidates() -> None:
    config = _config()
    references = [
        _episode("ref-1", "Budget Breakdown 101", 1),
        _episode("ref-2", "Missing Episode 202", 2),
    ]
    downloads = [
        _episode("dl-1", "Budget Breakdown 101", 1),
        _episode("dl-2", "Another Show Episode", 2),
    ]
    pairs = [(0, 0)]
    match_traces = _build_match_traces(references, downloads, pairs, config.name)
    result = MergeResult(
        config=config,
        references=references,
        downloads=downloads,
        match_traces=match_traces,
        pairs=pairs,
        episodes=[],
    )

    content = render_greedy_matches(result)

    assert "# Greedy Matches: Debug Show" in content
    assert "Below threshold" in content
    assert "## Unmatched Reference Candidates" in content