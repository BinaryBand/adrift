"""RSS feed regeneration for downloaded podcasts."""

from pathlib import Path

from src.catalog import match, process_feeds
from src.files.audio import is_audio
from src.files.s3 import get_s3_files, upload_file
from src.models import PodcastConfig, RssChannel, RssEpisode
from src.orchestration.download_client import _s3_prefix
from src.web.rss import podcast_to_rss


def _build_channel(config: PodcastConfig) -> RssChannel:
    from src.adapters import fetch_source_channel

    channel = RssChannel(
        title=config.name, author="", subtitle="", url="", description="", image=""
    )
    for source in config.references:
        try:
            _fill_channel(channel, fetch_source_channel(source))
        except Exception:
            pass
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
    config: PodcastConfig, episodes: list[RssEpisode], bucket: str, prefix: str
) -> list[RssEpisode]:
    files = _audio_files(get_s3_files(bucket, prefix))
    if not files:
        return []

    file_names = [Path(f).stem for f in files]
    titles = [ep.title for ep in episodes]
    pairs = match(file_names, titles, config.name)
    return _apply_pairs(files, episodes, pairs)


def _upload_rss(bucket: str, prefix: str, rss_xml: str) -> None:
    import tempfile as _tempfile

    with _tempfile.NamedTemporaryFile(suffix=".rss", delete=False) as f:
        f.write(rss_xml.encode())
        tmp_path = Path(f.name)
    try:
        upload_file(bucket, f"{prefix}/feed.rss", tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def update_rss(config: PodcastConfig) -> None:
    bucket, prefix = _s3_prefix(config)
    channel = _build_channel(config)
    ref_episodes = process_feeds(config)
    matched = _match_to_s3(config, ref_episodes, bucket, prefix)
    rss_xml = podcast_to_rss(channel, matched)
    _upload_rss(bucket, prefix, rss_xml)


__all__ = ["update_rss"]
