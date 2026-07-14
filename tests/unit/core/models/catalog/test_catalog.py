"""Tests for the episode collection and merging pipeline (catalog.py).

Covers the orchestration layer: _collect_episodes, _merge_episode_album,
process_feeds, process_sources, and the full pipeline that mirrors
_download_series in adrift/cli/download.py.

External I/O is patched at the source-fetch boundary:
  - src.catalog.get_rss_episodes
  - src.catalog.get_youtube_episodes
"""

import unittest
from unittest.mock import MagicMock, patch

from adrift.adapters import RegistryEpisodeSourceFactory
from adrift.core.models import EpisodeData, FeedSource, PodcastConfig, RssEpisode, SourceFilter
from adrift.core.services.catalog import (
    EpisodeFetchContext,
    MergeConfigOptions,
    align_episodes,
    merge_config,
)
from adrift.core.services.catalog import process_feeds as _process_feeds
from adrift.core.services.catalog import process_sources as _process_sources
from adrift.core.services.catalog.collection import _collect_episodes
from tests.unit.core.models.catalog._fixtures import dt as _dt
from tests.unit.core.models.catalog._fixtures import ep as _ep

# The production episode-source factory; injected everywhere the merge/collection
# pipeline used to reach the adapter registry directly (pre-inversion).
_FACTORY = RegistryEpisodeSourceFactory()


def process_feeds(config, callback=None, refresh_sources=False):
    return _process_feeds(
        config, callback, refresh_sources=refresh_sources, source_factory=_FACTORY
    )


def process_sources(config, callback=None, refresh_sources=False):
    return _process_sources(
        config, callback, refresh_sources=refresh_sources, source_factory=_FACTORY
    )


def _rss_source(
    url: str = "https://example.com/feed.rss", r_rules: list[str] | None = None
) -> FeedSource:
    return FeedSource(url=url, filters=SourceFilter(r_rules=r_rules or []))


def _yt_source(handle: str = "@testshow") -> FeedSource:
    return FeedSource(url=f"yt://{handle}")


def _config(
    name: str = "Test Show",
    references: list[FeedSource] | None = None,
    downloads: list[FeedSource] | None = None,
) -> PodcastConfig:
    return PodcastConfig(
        name=name,
        path="/media/podcasts/test-show",
        references=references or [],
        downloads=downloads or [],
    )


def _align_from_config(config: PodcastConfig) -> list[RssEpisode]:
    references = process_feeds(config)
    downloads = process_sources(config)
    pairs = align_episodes(references, downloads)
    return [downloads[d_idx] for _, d_idx in pairs]


def _pairs_from_config(config: PodcastConfig) -> list[tuple[int, int]]:
    return align_episodes(process_feeds(config), process_sources(config))


def _single_episode_config(mock_yt: MagicMock, mock_rss: MagicMock) -> PodcastConfig:
    mock_rss.return_value = [_ep("r1", "Ref Episode", pub_date=_dt(2024, 2, 6))]
    mock_yt.return_value = [_ep("d1", "Download Episode", pub_date=_dt(2024, 2, 6))]
    return _config(references=[_rss_source()], downloads=[_yt_source()])


class _FakeScoredAlignmentPort:
    def __init__(self, score: float = 0.99, track_calls: bool = False) -> None:
        self._score = score
        self._track_calls = track_calls
        self.called = False

    def align_with_scores(
        self,
        references,
        downloads,
        *,
        show="",
        alignment=None,
    ):
        if self._track_calls:
            self.called = True
        del references, downloads, show, alignment
        return [(0, 0)], {(0, 0): self._score}


# ---------------------------------------------------------------------------
# _collect_episodes / _merge_episode_album
# ---------------------------------------------------------------------------


class TestCollectEpisodes(unittest.TestCase):
    @patch("adrift.adapters.process.episode_sources.episode_source_rss.get_rss_episodes")
    def test_single_source_returns_all(self, mock_rss: MagicMock):
        eps = [_ep("1", "Ep 1"), _ep("2", "Ep 2"), _ep("3", "Ep 3")]
        mock_rss.return_value = eps
        context = EpisodeFetchContext(title="Test Show", is_reference=True, source_factory=_FACTORY)
        result = _collect_episodes([_rss_source()], context)
        assert len(result) == 3

    @patch("adrift.adapters.process.episode_sources.episode_source_rss.get_rss_episodes")
    def test_two_sources_deduplicates_overlap(self, mock_rss: MagicMock):
        ep1 = _ep("1", "Episode One", pub_date=_dt(2024, 2, 6))
        ep2 = _ep("2", "Episode Two", pub_date=_dt(2024, 2, 13))
        ep3 = _ep("3", "Episode Three", pub_date=_dt(2024, 2, 20))
        ep2_dup = _ep("2b", "Episode Two", pub_date=_dt(2024, 2, 13))  # same episode, second source
        mock_rss.side_effect = [[ep1, ep2], [ep2_dup, ep3]]
        context = EpisodeFetchContext(title="Test Show", is_reference=True, source_factory=_FACTORY)
        result = _collect_episodes(
            [
                _rss_source("https://a.com/feed.rss"),
                _rss_source("https://b.com/feed.rss"),
            ],
            context,
        )
        titles = [ep.title for ep in result]
        assert len(result) == 3
        assert titles.count("Episode Two") == 1

    @patch("adrift.adapters.process.episode_sources.episode_source_rss.get_rss_episodes")
    def test_two_sources_no_overlap(self, mock_rss: MagicMock):
        mock_rss.side_effect = [
            [_ep("1", "Episode One", pub_date=_dt(2024, 2, 6))],
            [_ep("2", "Episode Two", pub_date=_dt(2024, 2, 13))],
        ]
        context = EpisodeFetchContext(title="Test Show", is_reference=True, source_factory=_FACTORY)
        result = _collect_episodes(
            [
                _rss_source("https://a.com/feed.rss"),
                _rss_source("https://b.com/feed.rss"),
            ],
            context,
        )
        assert len(result) == 2

    def test_empty_sources_returns_empty(self):
        context = EpisodeFetchContext(title="Test Show", is_reference=True, source_factory=_FACTORY)
        result = _collect_episodes([], context)
        assert result == []


# ---------------------------------------------------------------------------
# process_feeds
# ---------------------------------------------------------------------------


class TestProcessFeeds(unittest.TestCase):
    @patch("adrift.adapters.process.episode_sources.episode_source_rss.get_rss_episodes")
    def test_rss_source_no_filter_returns_all(self, mock_rss: MagicMock):
        eps = [_ep(str(i), f"Ep {i}") for i in range(5)]
        mock_rss.return_value = eps
        result = process_feeds(_config(references=[_rss_source()]))
        assert len(result) == 5

    @patch("adrift.adapters.process.episode_sources.episode_source_rss.get_rss_episodes")
    def test_r_rules_forwarded_to_get_rss_episodes(self, mock_rss: MagicMock):
        """process_feeds must pass r_rules from config through to get_rss_episodes."""
        mock_rss.return_value = []
        rules = ["DTSTART:20240124T000000Z\nRRULE:FREQ=WEEKLY;BYDAY=TU"]
        process_feeds(_config(references=[_rss_source(r_rules=rules)]))
        # get_rss_episodes is now called via adapter with positional args
        # get_rss_episodes(url, filter_regex, r_rules, callback)
        assert mock_rss.call_args[0][2] == rules

    @patch("adrift.adapters.process.youtube.metadata.get_youtube_episodes")
    def test_youtube_source_returns_all(self, mock_yt: MagicMock):
        eps = [_ep("yt1", "YT Ep 1"), _ep("yt2", "YT Ep 2"), _ep("yt3", "YT Ep 3")]
        mock_yt.return_value = eps
        result = process_feeds(_config(references=[_yt_source()]))
        assert len(result) == 3

    @patch("adrift.adapters.process.episode_sources.episode_source_rss.get_rss_episodes")
    @patch("adrift.adapters.process.youtube.metadata.get_youtube_episodes")
    def test_multiple_sources_merged(self, mock_yt: MagicMock, mock_rss: MagicMock):
        mock_rss.return_value = [_ep("r1", "RSS Ep 1"), _ep("r2", "RSS Ep 2")]
        mock_yt.return_value = [_ep("yt1", "YT Ep 3")]
        result = process_feeds(_config(references=[_rss_source(), _yt_source()]))
        assert len(result) == 3

    def test_no_references_returns_empty(self):
        result = process_feeds(_config(references=[]))
        assert result == []


# ---------------------------------------------------------------------------
# process_sources
# ---------------------------------------------------------------------------


class TestProcessSources(unittest.TestCase):
    @patch("adrift.adapters.process.youtube.metadata.get_youtube_episodes")
    def test_returns_youtube_episodes(self, mock_yt: MagicMock):
        mock_yt.return_value = [_ep("yt1", "YT Ep A"), _ep("yt2", "YT Ep B")]
        result = process_sources(_config(downloads=[_yt_source()]))
        assert len(result) == 2

    def test_empty_downloads_returns_empty(self):
        result = process_sources(_config(downloads=[]))
        assert result == []


# ---------------------------------------------------------------------------
# Full pipeline: process_feeds + process_sources + align_episodes
# ---------------------------------------------------------------------------


class TestFullPipeline(unittest.TestCase):
    @patch("adrift.adapters.process.episode_sources.episode_source_rss.get_rss_episodes")
    @patch("adrift.adapters.process.youtube.metadata.get_youtube_episodes")
    def test_only_matched_downloads_survive(self, mock_yt: MagicMock, mock_rss: MagicMock):
        ep1 = _ep("r1", "The Show: Episode 101", pub_date=_dt(2024, 2, 6))
        ep2 = _ep("r2", "The Show: Episode 102", pub_date=_dt(2024, 2, 13))
        unrelated = _ep("d9", "Science Quarterly: Quantum Tunneling", pub_date=_dt(2016, 3, 1))

        mock_rss.return_value = [ep1, ep2]
        mock_yt.return_value = [
            _ep("d1", "The Show: Episode 101", pub_date=_dt(2024, 2, 6)),
            _ep("d2", "The Show: Episode 102", pub_date=_dt(2024, 2, 13)),
            unrelated,
        ]

        config = _config(references=[_rss_source()], downloads=[_yt_source()])
        survived = _align_from_config(config)

        assert len(survived) == 2
        survived_titles = {ep.title for ep in survived}
        assert "The Show: Episode 101" in survived_titles
        assert "The Show: Episode 102" in survived_titles
        assert "Science Quarterly: Quantum Tunneling" not in survived_titles

    @patch("adrift.adapters.process.episode_sources.episode_source_rss.get_rss_episodes")
    @patch("adrift.adapters.process.youtube.metadata.get_youtube_episodes")
    def test_merge_config_records_source_traces(self, mock_yt: MagicMock, mock_rss: MagicMock):
        mock_rss.return_value = [_ep("r1", "RSS Episode", pub_date=_dt(2024, 2, 6))]
        mock_yt.return_value = [_ep("d1", "YT Episode", pub_date=_dt(2024, 2, 6))]

        config = _config(
            references=[
                FeedSource(
                    url="https://example.com/feed.rss",
                    filters=SourceFilter(include=["Audit"]),
                )
            ],
            downloads=[_yt_source()],
        )

        from adrift.core.services.catalog import MergeConfigOptions

        result = merge_config(
            config,
            MergeConfigOptions(
                episode_source_factory=_FACTORY,
            ),
        )

        assert len(result.source_traces) == 2
        reference_trace = next(trace for trace in result.source_traces if trace.role == "reference")
        download_trace = next(trace for trace in result.source_traces if trace.role == "download")
        assert reference_trace.has_filters
        assert reference_trace.episode_count == 1
        assert reference_trace.source_type == "rss"
        assert not download_trace.has_filters
        assert download_trace.source_type == "youtube"

    @patch("adrift.adapters.process.episode_sources.episode_source_rss.get_rss_episodes")
    @patch("adrift.adapters.process.youtube.metadata.get_youtube_episodes")
    def test_merge_config_uses_injected_alignment_provider(
        self,
        mock_yt: MagicMock,
        mock_rss: MagicMock,
    ):
        mock_rss.return_value = [_ep("r1", "Ref Episode", pub_date=_dt(2024, 2, 6))]
        mock_yt.return_value = [_ep("d1", "Download Episode", pub_date=_dt(2024, 2, 6))]

        class FakeScoredAlignmentPort:
            def align_with_scores(
                self,
                references,
                downloads,
                *,
                show="",
                alignment=None,
            ):
                del references, downloads, show, alignment
                return [(0, 0)], {(0, 0): 0.91}

        class FakeAlignmentProvider:
            def __init__(self) -> None:
                self.calls: list[str | None] = []

            def get(self, backend_name=None):
                self.calls.append(backend_name)
                return FakeScoredAlignmentPort()

        provider = FakeAlignmentProvider()
        config = _config(references=[_rss_source()], downloads=[_yt_source()])

        from adrift.core.services.catalog import MergeConfigOptions

        result = merge_config(
            config,
            MergeConfigOptions(episode_source_factory=_FACTORY, alignment_provider=provider),
        )

        assert provider.calls
        assert all(backend is None for backend in provider.calls)
        assert result.pairs == [(0, 0)]

    @patch("adrift.adapters.process.episode_sources.episode_source_rss.get_rss_episodes")
    @patch("adrift.adapters.process.youtube.metadata.get_youtube_episodes")
    def test_merge_config_uses_injected_scored_alignment_port(
        self, mock_yt: MagicMock, mock_rss: MagicMock
    ):
        config = _single_episode_config(mock_yt, mock_rss)

        fake_port = _FakeScoredAlignmentPort(track_calls=True)
        result = merge_config(
            config,
            MergeConfigOptions(episode_source_factory=_FACTORY, scored_alignment_port=fake_port),
        )

        assert fake_port.called
        assert result.pairs == [(0, 0)]
        assert result.match_traces[0].matched_download_index == 0

    @patch("adrift.adapters.process.episode_sources.episode_source_rss.get_rss_episodes")
    @patch("adrift.adapters.process.youtube.metadata.get_youtube_episodes")
    def test_merge_config_uses_injected_batch_alignment_port(
        self, mock_yt: MagicMock, mock_rss: MagicMock
    ):
        config = _single_episode_config(mock_yt, mock_rss)

        class FakeBatchAlignmentPort:
            def __init__(self) -> None:
                self.called = False

            def align_batch(self, batch):
                self.called = True
                del batch
                return [(0, 0)], {(0, 0): 0.94}

        fake_port = FakeBatchAlignmentPort()
        result = merge_config(
            config,
            MergeConfigOptions(episode_source_factory=_FACTORY, scored_alignment_port=fake_port),
        )

        assert fake_port.called
        assert result.pairs == [(0, 0)]

    @patch("adrift.adapters.process.episode_sources.episode_source_rss.get_rss_episodes")
    @patch("adrift.adapters.process.youtube.metadata.get_youtube_episodes")
    def test_merge_config_runs_candidate_batch_alignment_port_in_ab_mode(
        self, mock_yt: MagicMock, mock_rss: MagicMock
    ):
        config = _single_episode_config(mock_yt, mock_rss)

        class CandidateBatchAlignmentPort:
            def __init__(self) -> None:
                self.called = False

            def align_batch(self, batch):
                self.called = True
                del batch
                return [(0, 0)], {(0, 0): 0.50}

        warnings: list[str] = []
        candidate = CandidateBatchAlignmentPort()

        merge_config(
            config,
            MergeConfigOptions(
                episode_source_factory=_FACTORY,
                scored_alignment_port=_FakeScoredAlignmentPort(),
                scored_alignment_candidate_port=candidate,
                ab_warnings=warnings,
            ),
        )

        assert candidate.called
        assert any("align_episodes.scores A/B mismatch" in warning for warning in warnings)

    @patch("adrift.adapters.process.episode_sources.episode_source_rss.get_rss_episodes")
    @patch("adrift.adapters.process.youtube.metadata.get_youtube_episodes")
    def test_merge_config_runs_candidate_episode_merger_port_in_ab_mode(
        self, mock_yt: MagicMock, mock_rss: MagicMock
    ):
        config = _single_episode_config(mock_yt, mock_rss)

        class PrimaryEpisodeMergerPort:
            def merge(self, references, downloads, pairs):
                del references, downloads, pairs
                return [
                    EpisodeData(
                        id="primary", title="Primary", description="primary", source=["primary"]
                    )
                ]

        class CandidateEpisodeMergerPort:
            def __init__(self) -> None:
                self.called = False

            def merge(self, references, downloads, pairs):
                self.called = True
                del references, downloads, pairs
                return [
                    EpisodeData(
                        id="candidate",
                        title="Candidate",
                        description="candidate",
                        source=["candidate"],
                    )
                ]

        warnings: list[str] = []
        candidate_port = CandidateEpisodeMergerPort()

        result = merge_config(
            config,
            MergeConfigOptions(
                episode_source_factory=_FACTORY,
                scored_alignment_port=_FakeScoredAlignmentPort(),
                episode_merger_port=PrimaryEpisodeMergerPort(),
                episode_merger_candidate_port=candidate_port,
                ab_warnings=warnings,
            ),
        )

        assert candidate_port.called
        assert result.episodes[0].id == "primary"
        assert any("merge_episodes A/B mismatch" in warning for warning in warnings)

    @patch("adrift.adapters.process.episode_sources.episode_source_rss.get_rss_episodes")
    @patch("adrift.adapters.process.youtube.metadata.get_youtube_episodes")
    def test_daily_show_scenario(self, mock_yt: MagicMock, mock_rss: MagicMock):
        """Regression: only episodes matching a reference should survive.

        Mirrors the bug where yt://@TheDailyShow downloaded 6,213 episodes
        despite references being filtered to ~5 post-2024 Tuesday episodes.
        """
        tuesdays = [
            _dt(2024, 1, 30),
            _dt(2024, 2, 6),
            _dt(2024, 2, 13),
            _dt(2024, 2, 20),
            _dt(2024, 2, 27),
        ]
        shared = [
            _ep(
                f"ref{i}",
                f"The Daily Show with Jon Stewart: Episode {i + 1}",
                pub_date=tuesdays[i],
            )
            for i in range(5)
        ]
        old_downloads = [
            _ep(
                f"old{i}",
                f"Old Daily Show Clip {i}",
                pub_date=_dt(2015 + i // 12, (i % 12) + 1, 1),
            )
            for i in range(95)
        ]

        mock_rss.return_value = list(shared)
        mock_yt.return_value = [
            _ep(f"yt{i}", ep.title, pub_date=ep.pub_date) for i, ep in enumerate(shared)
        ] + old_downloads

        config = _config(
            name="The Daily Show",
            references=[_rss_source()],
            downloads=[_yt_source("@TheDailyShow")],
        )
        survived = _align_from_config(config)

        assert len(survived) == 5
        for ep in survived:
            assert ep.pub_date is not None
            assert ep.pub_date >= _dt(2024, 1, 1), f"Old episode slipped through: {ep.title}"

    @patch("adrift.adapters.process.youtube.metadata.get_youtube_episodes")
    def test_no_references_keeps_all_downloads(self, mock_yt: MagicMock):
        """When references is empty, the fallback in download.py keeps all downloads."""
        mock_yt.return_value = [_ep("a", "Ep A"), _ep("b", "Ep B")]
        config = _config(references=[], downloads=[_yt_source()])

        references = process_feeds(config)
        downloads = process_sources(config)

        if references:
            pairs = align_episodes(references, downloads)
            survived = [downloads[d_idx] for _, d_idx in pairs]
        else:
            survived = downloads  # fallback branch from _download_series

        assert len(survived) == 2

    @patch("adrift.adapters.process.episode_sources.episode_source_rss.get_rss_episodes")
    @patch("adrift.adapters.process.youtube.metadata.get_youtube_episodes")
    def test_unmatched_reference_is_dropped(self, mock_yt: MagicMock, mock_rss: MagicMock):
        """A reference with no matching download produces no output episode."""
        mock_rss.return_value = [
            _ep(
                "ref_only",
                "Reference Only Episode: Exclusive Interview",
                pub_date=_dt(2024, 3, 1),
            )
        ]
        mock_yt.return_value = []

        config = _config(references=[_rss_source()], downloads=[_yt_source()])
        pairs = _pairs_from_config(config)

        assert pairs == []

    @patch("adrift.adapters.process.episode_sources.episode_source_rss.get_rss_episodes")
    @patch("adrift.adapters.process.youtube.metadata.get_youtube_episodes")
    def test_unmatched_download_is_dropped(self, mock_yt: MagicMock, mock_rss: MagicMock):
        """A download with no reference counterpart must not survive alignment."""
        matched_ref = _ep("ref1", "The Show: Episode 5", pub_date=_dt(2024, 3, 5))
        matched_dl = _ep("dl1", "The Show: Episode 5", pub_date=_dt(2024, 3, 5))
        orphan_dl = _ep("dl_only", "Download Only: Bonus Footage", pub_date=_dt(2016, 1, 1))

        mock_rss.return_value = [matched_ref]
        mock_yt.return_value = [matched_dl, orphan_dl]

        config = _config(references=[_rss_source()], downloads=[_yt_source()])
        pairs = _pairs_from_config(config)
        survived = [process_sources(config)[d_idx] for _, d_idx in pairs]

        survived_titles = {ep.title for ep in survived}
        assert "Download Only: Bonus Footage" not in survived_titles


if __name__ == "__main__":
    unittest.main()
