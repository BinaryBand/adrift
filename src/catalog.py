from rapidfuzz import fuzz
from pathlib import Path
from datetime import datetime

import sys

sys.path.insert(0, Path(__file__).parent.parent.as_posix())
from src.app_common import (
    MATCH_TOLERANCE,
    PodcastConfig,
    FeedSource,
)
from src.app_runner import normalize_title
from src.utils.progress import Callback
from src.web.rss import (
    RssChannel,
    RssEpisode,
    get_rss_channel,
    get_rss_episodes,
)
from src.utils.text import normalize_text, create_slug, is_youtube_channel
from src.youtube.metadata import get_youtube_channel, get_youtube_episodes
from src.models.output import EpisodeData


def _similarity_clean(ac: str, bc: str) -> float:
    """Similarity when inputs are already cleaned (lowercased, slugged)."""
    r = fuzz.ratio(ac, bc) / 100.0
    ts = fuzz.token_sort_ratio(ac, bc) / 100.0
    tset = fuzz.token_set_ratio(ac, bc) / 100.0
    return r * 0.4 + ts * 0.3 + tset * 0.3


def match(
    files: list[str],
    episodes: list[str],
    title: str,
    callback: Callback | None = None,
) -> list[tuple[int, int]]:
    files_clean, episodes_clean = _prepare_match_inputs(files, episodes, title)
    scores = _score_match_pairs(files_clean, episodes_clean, callback)
    matches = _select_unique_matches(scores)
    return _filter_tolerated_matches(matches, scores)


def _prepare_match_inputs(
    files: list[str], episodes: list[str], title: str
) -> tuple[list[str], list[str]]:
    files_clean = [normalize_text(f) for f in files]
    episodes_norm = [normalize_title(title, e) for e in episodes]
    episodes_clean = [normalize_text(e) for e in episodes_norm]
    return files_clean, episodes_clean


def _score_match_pairs(
    files_clean: list[str],
    episodes_clean: list[str],
    callback: Callback | None = None,
) -> dict[tuple[int, int], float]:
    scores: dict[tuple[int, int], float] = {}
    for f_idx, file_name in enumerate(files_clean):
        for e_idx, episode_name in enumerate(episodes_clean):
            scores[(f_idx, e_idx)] = _similarity_clean(file_name, episode_name)

        if callback:
            callback(f_idx + 1, len(files_clean))

    return scores


def _select_unique_matches(scores: dict[tuple[int, int], float]) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    used_files: set[int] = set()
    used_episodes: set[int] = set()
    pairs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    for (f_idx, e_idx), _score in pairs:
        if f_idx in used_files or e_idx in used_episodes:
            continue
        matches.append((f_idx, e_idx))
        used_files.add(f_idx)
        used_episodes.add(e_idx)
    return matches


def _filter_tolerated_matches(
    matches: list[tuple[int, int]], scores: dict[tuple[int, int], float]
) -> list[tuple[int, int]]:
    return [match for match in matches if scores[match] >= MATCH_TOLERANCE]


# ---------------------------------------------------------------------------
# Stage 1 — Similarity helpers (spec §"Stage 1 — Similarity Scoring")
# ---------------------------------------------------------------------------

_THUMBNAIL_RANK = {"maxres": 4, "hq": 3, "mq": 2, "sq": 1}

W_ID = 0.10
W_DATE = 0.30
W_TITLE = 0.50
W_DESC = 0.10


def sim_date(a: datetime | None, b: datetime | None) -> float:
    """Tiered date similarity per the spec."""
    if a is None or b is None:
        return 0.0
    delta = abs((a - b).days)
    if delta <= 2:
        return 1.00
    if delta <= 10:
        return 0.70
    if delta <= 35:
        return 0.15
    return 0.00


def _weighted_score(ref: RssEpisode, dl: RssEpisode) -> float:
    """4-signal weighted similarity score between two episodes."""
    s_id = 1.0 if ref.id and dl.id and ref.id == dl.id else 0.0
    s_date = sim_date(ref.pub_date, dl.pub_date)
    s_title = _similarity_clean(normalize_text(ref.title), normalize_text(dl.title))
    s_desc = _similarity_clean(
        normalize_text(ref.description or ""),
        normalize_text(dl.description or ""),
    )
    return W_ID * s_id + W_DATE * s_date + W_TITLE * s_title + W_DESC * s_desc


def align_episodes(
    references: list[RssEpisode], downloads: list[RssEpisode]
) -> list[tuple[int, int]]:
    """Greedy cross-alignment of reference and download episode lists.

    Returns a list of ``(ref_idx, dl_idx)`` index pairs for matched episodes
    with score ≥ MATCH_TOLERANCE (θ = 0.75 by default).
    """
    scores: dict[tuple[int, int], float] = {}
    for r_idx, ref in enumerate(references):
        for d_idx, dl in enumerate(downloads):
            scores[(r_idx, d_idx)] = _weighted_score(ref, dl)

    pairs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    matches: list[tuple[int, int]] = []
    used_refs: set[int] = set()
    used_dls: set[int] = set()

    for (r_idx, d_idx), score in pairs:
        if score < MATCH_TOLERANCE:
            break
        if r_idx not in used_refs and d_idx not in used_dls:
            matches.append((r_idx, d_idx))
            used_refs.add(r_idx)
            used_dls.add(d_idx)

    return matches


def _best_thumbnail(a: str | None, b: str | None) -> str | None:
    """Return the higher-resolution thumbnail inferred from URL keywords."""

    def _rank(url: str | None) -> int:
        if not url:
            return 0
        for kw, rank in _THUMBNAIL_RANK.items():
            if kw in url:
                return rank
        return 0  # generic URL, lowest priority above None

    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return a if _rank(a) >= _rank(b) else b


def merge_episode(ref: RssEpisode, dl: RssEpisode) -> EpisodeData:
    """Merge a reference + download episode pair into canonical EpisodeData."""
    # id: prefer non-URL id (YouTube IDs are short alphanumeric)
    id = ref.id if not ref.id.startswith("http") else dl.id

    # title: longest / most punctuated wins
    title = max([ref.title, dl.title], key=lambda t: (len(t), t.count(":")))

    # upload_date: earliest
    upload_date = min(
        (d for d in [ref.pub_date, dl.pub_date] if d is not None), default=None
    )

    # description: longest non-empty
    description = max([ref.description or "", dl.description or ""], key=len)

    thumbnail = _best_thumbnail(ref.image, dl.image)

    # source: union of all non-empty URLs
    source = list({u for u in [ref.content, dl.content] if u})

    return EpisodeData(
        id=id,
        title=title,
        description=description,
        source=source,
        thumbnail=thumbnail,
        upload_date=upload_date,
    )


# ---------------------------------------------------------------------------
# Episode collection helpers
# ---------------------------------------------------------------------------


def _collect_episodes(
    sources: list[FeedSource],
    title: str,
    is_reference: bool,
    callback: Callback | None = None,
) -> list[RssEpisode]:
    """Fetch and deduplicate episodes from a list of FeedSource objects."""
    albums = [
        _fetch_source_episodes(source, title, is_reference, callback)
        for source in sources
    ]

    if not albums:
        return []

    merged: list[RssEpisode] = albums[0]
    for album in albums[1:]:
        _merge_episode_album(merged, album, title, callback)

    return merged


def _fetch_source_episodes(
    source: FeedSource,
    title: str,
    is_reference: bool,
    callback: Callback | None = None,
) -> list[RssEpisode]:
    filter_regex = source.filters.to_regex()
    publish_days = source.filters.publish_days or None
    if is_youtube_channel(source.url):
        return get_youtube_episodes(
            source.url, title, filter_regex, is_reference, callback
        )
    return get_rss_episodes(source.url, filter_regex, publish_days, callback)


def _normalized_episode_titles(title: str, episodes: list[RssEpisode]) -> list[str]:
    return [normalize_title(title, episode.title) for episode in episodes]


def _duplicate_album_indices(
    merged: list[RssEpisode],
    album: list[RssEpisode],
    title: str,
    callback: Callback | None = None,
) -> set[int]:
    normalized_new = _normalized_episode_titles(title, album)
    normalized_existing = _normalized_episode_titles(title, merged)
    matched_indices = match(
        normalized_new, normalized_existing, create_slug(title), callback
    )
    return {album_idx for album_idx, _ in matched_indices}


def _merge_episode_album(
    merged: list[RssEpisode],
    album: list[RssEpisode],
    title: str,
    callback: Callback | None = None,
) -> None:
    duplicate_indices = _duplicate_album_indices(merged, album, title, callback)
    for index, episode in enumerate(album):
        if index not in duplicate_indices:
            merged.append(episode)


def process_channel(config: PodcastConfig) -> RssChannel:
    feed_channel: RssChannel = RssChannel(
        title=config.name,
        author="",
        subtitle="",
        description="",
        url="",
        image="",
    )

    for fs in config.references:
        feed_url = fs.url
        channel_rss: RssChannel
        if is_youtube_channel(feed_url):
            channel_rss = get_youtube_channel(feed_url, config.name)
        else:
            channel_rss = get_rss_channel(feed_url)

        # Prioritize data from the first feed: only fill if currently empty
        feed_channel.title = feed_channel.title or channel_rss.title
        feed_channel.author = feed_channel.author or channel_rss.author
        feed_channel.subtitle = feed_channel.subtitle or channel_rss.subtitle
        feed_channel.description = feed_channel.description or channel_rss.description
        feed_channel.url = feed_channel.url or channel_rss.url
        feed_channel.image = feed_channel.image or channel_rss.image

    return feed_channel


def _process_source(
    source: str,
    title: str,
    filter: str | None = None,
    feed_day_of_week_filter: list[str] | None = None,
    callback: Callback | None = None,
) -> list[RssEpisode]:
    episodes: list[RssEpisode] = []
    if is_youtube_channel(source):
        episodes = get_youtube_episodes(source, title, filter, False, callback)
    else:
        episodes = get_rss_episodes(source, filter, feed_day_of_week_filter, callback)

    return episodes


def process_sources(
    config: PodcastConfig,
    callback: Callback | None = None,
) -> list[RssEpisode]:
    """Collect and deduplicate download-side episodes (thin wrapper)."""
    episodes = _collect_episodes(config.downloads, config.name, False, callback)
    if callback:
        callback(len(episodes), len(episodes))
    return episodes


def process_feeds(
    config: PodcastConfig, callback: Callback | None = None
) -> list[RssEpisode]:
    """Collect and deduplicate reference-side episodes (thin wrapper)."""
    title = config.name
    source_episodes = _collect_episodes(config.references, title, True, callback)

    return source_episodes
