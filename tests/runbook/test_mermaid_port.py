from datetime import datetime, timezone
from pathlib import Path

from src.adapters.mermaid import FileMermaidAdapter
from src.app_common import FeedSource, PodcastConfig
from src.models.metadata import RssEpisode
from src.models.output import EpisodeData
from src.models.pipeline import MergeResult, SourceTrace
from src.ports.mermaid import MermaidRenderOptions


def _config() -> PodcastConfig:
    return PodcastConfig(
        name="Example Show",
        references=[FeedSource(url="https://example.com/reference.rss")],
        downloads=[FeedSource(url="https://www.youtube.com/@example")],
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


def test_mermaid_writes_file_and_contains_mermaid(tmp_path: Path) -> None:
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

    adapter = FileMermaidAdapter()
    out_paths = adapter.generate_diagrams(result, tmp_path)

    assert len(out_paths) == 1
    p = out_paths[0]
    assert p.exists()
    content = p.read_text()
    assert "# Alignment Summary: Example Show" in content
    assert "```mermaid" in content
    assert "sankey-beta" in content
    assert "Reference Episodes (1),Matched References (1),1" in content
    assert "Download Episodes (1),Matched Downloads (1),1" in content
    assert "Matched References (1),Merged Episodes for Example Show (1),1" in content


def test_mermaid_groups_unmatched_counts(tmp_path: Path) -> None:
    config = _config()
    references = [
        _rss_episode("ref-1", "Reference Episode 1", "https://example.com/reference-1.mp3"),
        _rss_episode("ref-2", "Reference Episode 2", "https://example.com/reference-2.mp3"),
    ]
    downloads = [_rss_episode("dl-1", "Download Episode", "https://youtube.com/watch?v=abc123")]
    merged = [_merged_episode()]
    result = MergeResult(
        config=config,
        references=references,
        downloads=downloads,
        pairs=[(0, 0)],
        episodes=merged,
    )

    adapter = FileMermaidAdapter()
    out_paths = adapter.generate_diagrams(result, tmp_path)

    content = out_paths[0].read_text()
    assert "Reference Episodes (2),Unmatched References (1),1" in content
    assert "Unmatched Downloads" not in content
    assert "Reference Episodes (2),Matched References (1),1" in content
    assert "Download Episodes (1),Matched Downloads (1),1" in content


def test_mermaid_overwrite_respected(tmp_path: Path) -> None:
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

    out_dir = tmp_path / config.slug / "feeds"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "alignment_sankey.md"
    pre = "PREVIOUS"
    path.write_text(pre, encoding="utf-8")

    adapter = FileMermaidAdapter()
    adapter.generate_diagrams(
        result,
        tmp_path,
        MermaidRenderOptions(overwrite=False),
    )

    assert path.read_text(encoding="utf-8") == pre


def test_mermaid_includes_filter_stage_when_source_traces_exist(tmp_path: Path) -> None:
    config = PodcastConfig(
        name="Filtered Show",
        references=[
            FeedSource(
                url="https://example.com/reference.rss",
                filters={"include": ["audit"]},
            )
        ],
        downloads=[FeedSource(url="https://www.youtube.com/@example")],
    )
    references = [_rss_episode("ref-1", "Reference Episode", "https://example.com/reference-1.mp3")]
    downloads = [_rss_episode("dl-1", "Download Episode", "https://youtube.com/watch?v=abc123")]
    merged = [_merged_episode()]
    result = MergeResult(
        config=config,
        references=references,
        downloads=downloads,
        source_traces=[
            SourceTrace(
                role="reference",
                url="https://example.com/reference.rss",
                source_type="rss",
                episode_count=1,
                filters=config.references[0].filters,
                has_filters=True,
            ),
            SourceTrace(
                role="download",
                url="https://www.youtube.com/@example",
                source_type="youtube",
                episode_count=1,
                filters=config.downloads[0].filters,
                has_filters=False,
            ),
        ],
        pairs=[(0, 0)],
        episodes=merged,
    )

    content = FileMermaidAdapter().generate_diagrams(result, tmp_path)[0].read_text()
    assert "Reference Source Episodes (1),Reference Episodes from Filtered Sources (1),1" in content
    assert "Reference Episodes from Filtered Sources (1),Reference Episodes (1),1" in content
    assert "Download Source Episodes (1),Download Episodes from Unfiltered Sources (1),1" in content
