"""RSS feed regeneration for downloaded podcasts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from src.catalog import match, process_feeds
from src.files.audio import is_audio
from src.models import PodcastConfig, RssChannel, RssEpisode
from src.orchestration.download_client import s3_prefix
from src.web.rss import podcast_to_rss

if TYPE_CHECKING:
    from src.application.context import AppContext


logger = logging.getLogger(__name__)
_CHANNEL_FILL_ERRORS = (OSError, RuntimeError, TypeError, ValueError)


def _build_channel(config: PodcastConfig) -> RssChannel:
    from src.adapters import get_episode_source_adapter

    channel = RssChannel(
        title=config.name, author="", subtitle="", url="", description="", image=""
    )
    for source in config.references:
        try:
            _fill_channel(channel, get_episode_source_adapter(source).fetch_channel(source))
        except _CHANNEL_FILL_ERRORS as exc:
            logger.warning("Unable to fill channel metadata from source %s: %s", source.url, exc)
    return channel


def _fill_channel(base: RssChannel, incoming: RssChannel) -> None:
    for field in ("title", "author", "subtitle", "description", "url", "image"):
        if not getattr(base, field):
            setattr(base, field, getattr(incoming, field))


def _audio_files(files: list[str]) -> list[str]:
    return [f for f in files if is_audio(f)]


def _apply_pairs(
    files: list[str], episodes: list[RssEpisode], pairs: list[tuple[int, int]]
) -> list[RssEpisode]:
    matched: list[RssEpisode] = []
    for f_idx, e_idx in pairs:
        src = episodes[e_idx]
        ep = RssEpisode(
            id=src.id,
            title=src.title,
            author=src.author,
            content=files[f_idx],
            description=src.description,
            duration=src.duration,
            pub_date=src.pub_date,
            image=src.image,
        )
        matched.append(ep)
    return matched


def _match_to_s3(
    config: PodcastConfig,
    episodes: list[RssEpisode],
    ctx: AppContext,
) -> list[RssEpisode]:
    bucket, prefix = s3_prefix(config)
    s3 = cast(Any, ctx.s3)
    files = _audio_files(s3.get_s3_files(bucket, prefix))
    if not files:
        return []

    file_names = [Path(f).stem for f in files]
    titles = [ep.title for ep in episodes]
    pairs = match(file_names, titles, config.name)
    return _apply_pairs(files, episodes, pairs)


def _upload_rss(bucket: str, prefix: str, rss_xml: str, ctx: AppContext) -> None:
    import tempfile as _tempfile

    with _tempfile.NamedTemporaryFile(suffix=".rss", delete=False) as f:
        f.write(rss_xml.encode())
        tmp_path = Path(f.name)
    try:
        cast(Any, ctx.s3).upload_file((bucket, f"{prefix}/feed.rss"), tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def update_rss(config: PodcastConfig, ctx: AppContext) -> None:
    bucket, prefix = s3_prefix(config)
    channel = _build_channel(config)
    ref_episodes = process_feeds(config)
    matched = _match_to_s3(config, ref_episodes, ctx)
    rss_xml = podcast_to_rss(channel, matched)
    _upload_rss(bucket, prefix, rss_xml, ctx)


__all__ = ["update_rss"]
