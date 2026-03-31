from typing import Literal, cast
from pydantic import BaseModel
from rapidfuzz import fuzz
from pathlib import Path

import pandas as pd
import sys

sys.path.insert(0, Path(__file__).parent.parent.as_posix())
from src.app_common import DAY_OF_WEEK, MATCH_TOLERANCE, MatchData, PodcastData
from src.app_runner import normalize_title
from src.utils.progress import Callback
from src.web.rss import (
    RssChannel,
    RssEpisode,
    get_rss_channel,
    get_rss_episodes,
    rss_to_df,
)
from src.utils.text import normalize_text, create_slug, is_youtube_channel
from src.youtube.metadata import get_youtube_channel, get_youtube_episodes


def _update_logs(title: str, match: list):
    # NOTE: pydantic BaseModel instances are iterable (yielding (field, value)
    # tuples). Passing them directly to DataFrame produces 0/1/2 columns of
    # stringified tuples instead of real columns like file/episode/score.
    rows: list[dict] = []
    for item in match:
        if isinstance(item, BaseModel):
            rows.append(item.model_dump())
        elif isinstance(item, dict):
            rows.append(item)
        else:
            try:
                rows.append(dict(item))
            except Exception:
                rows.append({"value": str(item)})

    df = pd.DataFrame(rows)
    cols = [c for c in ("file", "episode", "score", "baseline") if c in df.columns]
    other = [c for c in df.columns if c not in cols]
    df = df[cols + other]

    df_label = f"{create_slug(title)}_match"
    print(f"DataFrame: {df_label}")


def similarity(a: str, b: str) -> float:
    ac = normalize_text(a)
    bc = normalize_text(b)

    base = 0.0
    r = fuzz.ratio(ac, bc) / 100.0
    ts = fuzz.token_sort_ratio(ac, bc) / 100.0
    tset = fuzz.token_set_ratio(ac, bc) / 100.0
    base = r * 0.4 + ts * 0.3 + tset * 0.3

    return base


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
    files_clean = [normalize_text(f) for f in files]
    episodes_norm = [normalize_title(title, e) for e in episodes]
    episodes_clean = [normalize_text(e) for e in episodes_norm]

    scores = {}
    for f_idx, ac in enumerate(files_clean):
        for e_idx, bc in enumerate(episodes_clean):
            score = _similarity_clean(ac, bc)
            scores[(f_idx, e_idx)] = score

        if callback:
            callback(f_idx + 1, len(files))

    # Greedily select best matches, ensuring no duplicates
    matches, used_files, used_episodes = [], set(), set()
    pairs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    for (f_idx, e_idx), score in pairs:
        if f_idx not in used_files and e_idx not in used_episodes:
            matches.append((f_idx, e_idx))
            used_files.add(f_idx)
            used_episodes.add(e_idx)

    match_data: list[MatchData] = [
        MatchData(file=files[f], episode=episodes[e], score=scores[(f, e)])
        for f, e in matches
    ]

    # Include unmatched files (no episode paired)
    matched_file_indices = {f for f, _ in matches}
    for f_idx, f_name in enumerate(files):
        if f_idx not in matched_file_indices:
            match_data.append(MatchData(file=f_name, episode=None, score=0.0))

    # Include unmatched episodes (no file paired)
    matched_episode_indices = {e for _, e in matches}
    for e_idx, e_name in enumerate(episodes):
        if e_idx not in matched_episode_indices:
            match_data.append(MatchData(file=None, episode=e_name, score=0.0))
    _update_logs(create_slug(title), match_data)

    return [m for m in matches if scores[m] >= MATCH_TOLERANCE]


def process_channel(config: PodcastData) -> RssChannel:
    feed_channel: RssChannel = RssChannel(
        title=config.title,
        author="",
        subtitle="",
        description="",
        url="",
        image="",
    )

    for feed_url in config.feeds:
        channel_rss: RssChannel
        if is_youtube_channel(feed_url):
            channel_rss = get_youtube_channel(feed_url, config.title)
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
    feed_day_of_week_filter: list[DAY_OF_WEEK] | None = None,
    callback: Callback | None = None,
) -> list[RssEpisode]:
    episodes: list[RssEpisode] = []
    if is_youtube_channel(source):
        episodes = get_youtube_episodes(source, title, filter, False, callback)
    else:
        episodes = get_rss_episodes(source, filter, feed_day_of_week_filter, callback)

    return episodes


def process_sources(
    config: PodcastData,
    callback: Callback | None = None,
) -> list[RssEpisode]:
    active = config.source_filters or config.filters
    filter_regex = active.to_regex()
    publish_days = active.publish_days or None

    episodes_by_source: list[list[RssEpisode]] = []
    for source in config.sources:
        eps = _process_source(
            source,
            config.title,
            filter_regex,
            publish_days,
            callback,
        )
        episodes_by_source.append(eps)
    episodes = [ep for episodes in episodes_by_source for ep in episodes]

    if callback:
        callback(len(episodes), len(episodes))

    return episodes


def process_feeds(
    config: PodcastData, callback: Callback | None = None
) -> list[RssEpisode]:
    title = config.title
    active = config.feed_filters or config.filters
    filter = active.to_regex()
    feed_day_of_week_filter = active.publish_days or None

    albums: list[list[RssEpisode]] = []
    for source in config.feeds:
        print(f"Processing feed source: {source}")
        episodes: list[RssEpisode] = []
        if is_youtube_channel(source):
            episodes = get_youtube_episodes(source, title, filter, True, callback)
        else:
            episodes = get_rss_episodes(
                source, filter, feed_day_of_week_filter, callback
            )
        albums.append(episodes)

    if not albums:
        return []

    source_episodes: list[RssEpisode] = albums[0]
    for album in albums[1:]:
        existing_titles = [ep.title for ep in source_episodes]
        new_titles = [ep.title for ep in album]

        # Normalize titles before matching to ensure consistent scoring
        normalized_new = [normalize_title(title, t) for t in new_titles]
        normalized_existing = [normalize_title(title, t) for t in existing_titles]

        matched_indices = match(
            normalized_new, normalized_existing, create_slug(title), callback
        )

        # Only add non-duplicate episodes
        duplicate_indices = set({f_idx for f_idx, _ in matched_indices})
        for i, episode in enumerate(album):
            if i not in duplicate_indices:
                source_episodes.append(episode)

        if callback:
            callback(len(source_episodes), sum(len(a) for a in albums))

    df = rss_to_df(source_episodes)
    print(f"DataFrame: {create_slug(title)}_catalog")

    return source_episodes
