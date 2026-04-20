"""Three-stage download pipeline: enrich → download/upload → update RSS."""

import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from src.app_common import PodcastConfig
from src.catalog import match, process_feeds
from src.files.audio import convert_to_opus, cut_segments, get_duration, is_audio
from src.files.s3 import UploadOptions, exists, get_file_list, get_metadata, upload_file
from src.models import MediaMetadata, RssChannel, RssEpisode
from src.models.pipeline import DownloadEpisode, MergeResult
from src.utils.progress import Callback
from src.utils.regex import YOUTUBE_VIDEO_REGEX
from src.web.rss import download_direct, podcast_to_rss
from src.web.sponsorblock import fetch_sponsor_segments
from src.youtube.downloader import download_video

# ---------------------------------------------------------------------------
# Stage 1 — enrich MergeResult with sponsor segments
# ---------------------------------------------------------------------------


def enrich_with_sponsors(result: MergeResult) -> list[DownloadEpisode]:
    """Pair each download-side episode with its sponsor segments."""
    episodes: list[DownloadEpisode] = []
    for _ref_idx, dl_idx in result.pairs:
        ep = result.downloads[dl_idx]
        video_id = _extract_video_id(ep.content)
        segments = fetch_sponsor_segments(video_id) if video_id else []
        episodes.append(DownloadEpisode(episode=ep, sponsor_segments=segments, video_id=video_id))
    result.download_episodes = episodes
    return episodes


def _extract_video_id(content: str) -> str | None:
    m = YOUTUBE_VIDEO_REGEX.search(content)
    return m.group(4) if m else None


@dataclass(frozen=True)
class DownloadQueueItem:
    episode: DownloadEpisode
    exists_on_s3: bool


@dataclass(frozen=True)
class DownloadProgressHooks:
    on_operation: Callable[[str], None] | None = None
    on_progress: Callback | None = None
    on_complete: Callable[[], None] | None = None


@dataclass(frozen=True)
class _UploadRequest:
    bucket: str
    key: str
    opus: Path
    metadata: MediaMetadata


def build_download_queue(
    episodes: list[DownloadEpisode], config: PodcastConfig
) -> list[DownloadQueueItem]:
    queue = [
        DownloadQueueItem(
            episode=episode,
            exists_on_s3=_episode_exists_on_s3(episode, config),
        )
        for episode in episodes
    ]
    return sorted(queue, key=_download_queue_sort_key)


def _episode_exists_on_s3(ep: DownloadEpisode, config: PodcastConfig) -> bool:
    bucket, prefix = _s3_prefix(config)
    key_prefix = f"{prefix}/{_episode_slug(config, ep)}"
    if exists(bucket, key_prefix) is not None:
        return True
    return _existing_media_sources(bucket, prefix).matches(ep)


@dataclass(frozen=True)
class _ExistingMediaSources:
    source_urls: frozenset[str]
    youtube_video_ids: frozenset[str]

    def matches(self, ep: DownloadEpisode) -> bool:
        if ep.episode.content in self.source_urls:
            return True
        return ep.video_id is not None and ep.video_id in self.youtube_video_ids


@lru_cache(maxsize=128)
def _existing_media_sources(bucket: str, prefix: str) -> _ExistingMediaSources:
    source_urls: set[str] = set()
    youtube_video_ids: set[str] = set()

    for name in get_file_list(bucket, prefix, False):
        metadata = get_metadata(bucket, _prefixed_s3_key(prefix, name))
        if metadata is None:
            continue
        source_urls.add(metadata.source)
        if video_id := _extract_video_id(metadata.source):
            youtube_video_ids.add(video_id)

    return _ExistingMediaSources(frozenset(source_urls), frozenset(youtube_video_ids))


def _prefixed_s3_key(prefix: str, name: str) -> str:
    return f"{prefix}/{name}" if prefix else name


def _download_queue_sort_key(item: DownloadQueueItem) -> tuple[bool, float, str]:
    episode = item.episode.episode
    return (
        item.exists_on_s3,
        -_episode_sort_timestamp(episode.pub_date),
        episode.title,
    )


def _episode_sort_timestamp(pub_date: datetime | None) -> float:
    if pub_date is None:
        return datetime.min.replace(tzinfo=timezone.utc).timestamp()
    if pub_date.tzinfo is None:
        pub_date = pub_date.replace(tzinfo=timezone.utc)
    return pub_date.timestamp()


# ---------------------------------------------------------------------------
# Stage 2 — download, cut ads, convert, upload
# ---------------------------------------------------------------------------


def download_and_upload(
    ep: DownloadEpisode,
    config: PodcastConfig,
    progress_hooks: DownloadProgressHooks | None = None,
) -> bool:
    """Download one episode, remove ads, convert to Opus, upload to S3.

    Returns True if newly uploaded, False if already present on S3.
    """
    bucket, prefix = _s3_prefix(config)
    key_prefix = f"{prefix}/{_episode_slug(config, ep)}"
    if exists(bucket, key_prefix):
        return False
    with tempfile.TemporaryDirectory() as tmp:
        return _process_in_tmpdir(ep, config, Path(tmp), progress_hooks)


def _process_in_tmpdir(
    ep: DownloadEpisode,
    config: PodcastConfig,
    tmp: Path,
    progress_hooks: DownloadProgressHooks | None,
) -> bool:
    bucket, prefix = _s3_prefix(config)
    key_prefix = f"{prefix}/{_episode_slug(config, ep)}"
    audio = _download_episode_audio(ep, tmp, progress_hooks)
    if audio is None:
        _complete_operation(progress_hooks)
        return False
    opus = _prepare_upload_audio(ep, audio, progress_hooks)
    duration = get_duration(opus)
    metadata = _build_metadata(ep, duration, sponsors_removed=bool(ep.sponsor_segments))
    upload_request = _build_upload_request(bucket, key_prefix, opus, metadata)
    _upload_episode_audio(ep, upload_request, progress_hooks)
    _complete_operation(progress_hooks)
    return True


def _download_episode_audio(
    ep: DownloadEpisode,
    tmp: Path,
    progress_hooks: DownloadProgressHooks | None,
) -> Path | None:
    _start_operation(progress_hooks, f"download audio: {ep.episode.title}")
    return _download_audio(ep, tmp, _operation_progress(progress_hooks))


def _prepare_upload_audio(
    ep: DownloadEpisode,
    audio: Path,
    progress_hooks: DownloadProgressHooks | None,
) -> Path:
    if ep.sponsor_segments:
        _start_operation(progress_hooks, f"cut sponsors: {ep.episode.title}")
        cut_segments(audio, ep.sponsor_segments, callback=_operation_progress(progress_hooks))
    _start_operation(progress_hooks, f"convert opus: {ep.episode.title}")
    return convert_to_opus(audio, callback=_operation_progress(progress_hooks))


def _build_upload_request(
    bucket: str,
    key_prefix: str,
    opus: Path,
    metadata: MediaMetadata,
) -> _UploadRequest:
    return _UploadRequest(
        bucket=bucket,
        key=f"{key_prefix}.opus",
        opus=opus,
        metadata=metadata,
    )


def _upload_episode_audio(
    ep: DownloadEpisode,
    request: _UploadRequest,
    progress_hooks: DownloadProgressHooks | None,
) -> None:
    _start_operation(progress_hooks, f"upload opus: {ep.episode.title}")
    upload_file(
        request.bucket,
        request.key,
        request.opus,
        UploadOptions(metadata=request.metadata, callback=_operation_progress(progress_hooks)),
    )


def _start_operation(progress_hooks: DownloadProgressHooks | None, label: str) -> None:
    if progress_hooks is not None and progress_hooks.on_operation is not None:
        progress_hooks.on_operation(label)


def _complete_operation(progress_hooks: DownloadProgressHooks | None) -> None:
    if progress_hooks is not None and progress_hooks.on_complete is not None:
        progress_hooks.on_complete()


def _operation_progress(progress_hooks: DownloadProgressHooks | None) -> Callback | None:
    if progress_hooks is None:
        return None
    return progress_hooks.on_progress


def _episode_slug(config: PodcastConfig, ep: DownloadEpisode) -> str:
    from src.app_runner import normalize_title

    return normalize_title(config.name, ep.episode.title)


def _download_audio(
    ep: DownloadEpisode, dest: Path, callback: Callback | None = None
) -> Path | None:
    if ep.video_id:
        return download_video(ep.episode.content, dest, callback=callback)
    return download_direct(ep.episode.content, dest)


def _build_metadata(
    ep: DownloadEpisode, duration: float | None, *, sponsors_removed: bool
) -> MediaMetadata:
    from datetime import datetime, timezone

    pub_date = ep.episode.pub_date or datetime.now(tz=timezone.utc)
    return MediaMetadata(
        duration=duration or 0.0,
        source=ep.episode.content,
        upload_date=pub_date,
        sponsors_removed=sponsors_removed,
    )


# ---------------------------------------------------------------------------
# Stage 3 — regenerate and upload RSS feed
# ---------------------------------------------------------------------------


def update_rss(config: PodcastConfig) -> None:
    """Rebuild and upload the podcast RSS feed from matched S3 audio files."""
    bucket, prefix = _s3_prefix(config)
    channel = _build_channel(config)
    ref_episodes = process_feeds(config)
    matched = _match_to_s3(config, ref_episodes, bucket, prefix)
    rss_xml = podcast_to_rss(channel, matched)
    _upload_rss(bucket, prefix, rss_xml)


def _build_channel(config: PodcastConfig) -> RssChannel:
    from src.adapters import get_episode_source_adapter

    channel = RssChannel(
        title=config.name, author="", subtitle="", url="", description="", image=""
    )
    for source in config.references:
        try:
            adapter = get_episode_source_adapter(source)
            _fill_channel(channel, adapter.fetch_channel(source))
        except Exception:
            pass
    return channel


def _fill_channel(base: RssChannel, incoming: RssChannel) -> None:
    for field in ("title", "author", "subtitle", "description", "url", "image"):
        if not getattr(base, field):
            setattr(base, field, getattr(incoming, field))


def _match_to_s3(
    config: PodcastConfig, episodes: list[RssEpisode], bucket: str, prefix: str
) -> list[RssEpisode]:
    from src.app_runner import get_s3_files

    files = _audio_files(get_s3_files(bucket, prefix))
    if not files:
        return []

    file_names = [Path(f).stem for f in files]
    titles = [ep.title for ep in episodes]
    pairs = match(file_names, titles, config.name)
    return _apply_pairs(files, episodes, pairs)


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


def _upload_rss(bucket: str, prefix: str, rss_xml: str) -> None:
    import tempfile as _tempfile

    with _tempfile.NamedTemporaryFile(suffix=".rss", delete=False) as f:
        f.write(rss_xml.encode())
        tmp_path = Path(f.name)
    try:
        upload_file(bucket, f"{prefix}/feed.rss", tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _s3_prefix(config: PodcastConfig) -> tuple[str, str]:
    """Parse config.path '/media/podcasts/slug' → ('media', 'podcasts/slug')."""
    parts = Path(config.path).parts
    return parts[1], "/".join(parts[2:])
