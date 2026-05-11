from datetime import datetime, timezone
from pathlib import Path

from runbook import audit_alignment as audit
from src.models import FeedSource, PodcastConfig, RssEpisode


def _episode(identifier: str, title: str) -> RssEpisode:
    return RssEpisode(
        id=identifier,
        title=title,
        author="",
        content=f"https://example.com/{identifier}",
        description="",
        pub_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _config() -> PodcastConfig:
    return PodcastConfig(
        name="Audit Show",
        path="/tmp/audit-show",
        references=[FeedSource(url="https://example.com/reference.rss")],
        downloads=[FeedSource(url="yt://@audit-show")],
    )


def test_build_audit_rows_no_downloads() -> None:
    references = [_episode("r1", "Episode 1")]
    frame = audit._AuditFrame(
        references=references,
        downloads=[],
        scores={},
        matched_pairs=set(),
        match_tolerance=0.75,
        borderline_min=0.60,
    )

    rows = audit._build_audit_rows(frame)

    assert len(rows) == 1
    assert rows[0].category == "NO_DOWNLOAD"


def test_build_audit_rows_classifications() -> None:
    references = [
        _episode("r1", "Episode 10: The Case"),
        _episode("r2", "Episode 2: Part Two"),
        _episode("r3", "Listener Tales 92"),
        _episode("r4", "Listener Tales 92 Extended"),
        _episode("r5", "Completely Different"),
    ]
    downloads = [
        _episode("d1", "Episode 10 The Case"),
        _episode("d2", "Episode 3: Part Two"),
        _episode("d3", "Listener Tales 92 | Morbid | Podcast"),
    ]
    scores = {
        (0, 0): 0.95,
        (1, 1): 0.89,
        (2, 2): 0.74,
        (3, 2): 0.93,
    }
    frame = audit._AuditFrame(
        references=references,
        downloads=downloads,
        scores=scores,
        matched_pairs={(0, 0), (3, 2)},
        match_tolerance=0.75,
        borderline_min=0.60,
    )

    rows = audit._build_audit_rows(frame)
    categories = [row.category for row in rows]

    assert categories == [
        "MATCHED",
        "SERIES_MISMATCH",
        "REUSED_TARGET",
        "REUSED_TARGET",
        "UNCLEAR",
    ]


def test_diff_against_gold_uses_expected_fixture(tmp_path: Path, monkeypatch) -> None:
    slug = "audit-show"
    fixture_root = tmp_path / "tests" / "resources" / "alignment"
    fixture_root.mkdir(parents=True)
    expected = fixture_root / f"{slug}_audit.csv"
    expected.write_text(
        "ref_id,ref_title,best_dl_id,best_dl_title,score,category,notes\n"
        "r1,Episode 1,d1,Episode 1,0.9000,MATCHED,Selected by greedy matcher\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    rows = [
        audit.AuditRow(
            ref_id="r1",
            ref_title="Episode 1",
            best_dl_id="d1",
            best_dl_title="Episode 1",
            score=0.9,
            category="MATCHED",
            notes="Selected by greedy matcher",
        )
    ]

    ok, summary = audit._diff_against_gold(slug, rows)

    assert ok is True
    assert summary == ""


def test_promote_benchmark_adds_only_confirmed_rows(tmp_path: Path, monkeypatch) -> None:
    config = _config()
    fixture_root = tmp_path / "tests" / "resources" / "alignment"
    fixture_root.mkdir(parents=True)
    benchmark = fixture_root / f"{config.slug}_benchmark.csv"
    benchmark.write_text(
        "label,reference_title,download_title\ntrue,Existing Match,Existing Match\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    rows = [
        audit.AuditRow("r1", "Existing Match", "d1", "Existing Match", 0.95, "MATCHED"),
        audit.AuditRow("r2", "New Match", "d2", "New Match", 0.92, "MATCHED"),
        audit.AuditRow("r3", "Mismatch Ref", "d3", "Mismatch Dl", 0.88, "SERIES_MISMATCH"),
        audit.AuditRow("r4", "Borderline", "d4", "Borderline Dl", 0.66, "BORDERLINE"),
    ]

    added = audit._promote_benchmark(config.slug, rows)
    payload = benchmark.read_text(encoding="utf-8")

    assert added == 2
    assert "true,New Match,New Match" in payload
    assert "false,Mismatch Ref,Mismatch Dl" in payload
    assert "Borderline" not in payload
