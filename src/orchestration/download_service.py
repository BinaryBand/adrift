from __future__ import annotations

import os
import random
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from random import shuffle
from typing import Callable

from tqdm import tqdm

import src.youtube.downloader as yt_downloader
from src.app_common import PodcastConfig, ensure_podcast_config, load_podcasts_config
from src.app_runner import get_s3_files, normalize_title
from src.catalog import align_episodes, match, process_channel, process_feeds, process_sources
from src.files.audio import convert_to_opus, get_duration, is_audio
from src.files.s3 import download_file, exists, upload_file
from src.models import DEVICE, MediaMetadata
from src.orchestration.models import (
    DownloadRunRequest,
    DownloadRunResult,
    FailedSeries,
    LogCallback,
)
from src.utils.progress import get_callback
from src.utils.regex import YOUTUBE_VIDEO_REGEX
from src.web.rss import RssChannel, RssEpisode, download_direct, podcast_to_rss
from src.web.sponsorblock import fetch_sponsor_segments, remove_sponsors
from src.youtube.downloader import BotDetectionError, download_video
from src.youtube.metadata import get_video_info


@dataclass
class _DownloadContext:
    config: PodcastConfig
    bucket: str
    prefix: Path


@dataclass
class _PipelineState:
    remaining: int | None
    total_downloaded: int = 0
    failed_series: list[FailedSeries] = field(default_factory=list)
    bot_detected: bool = False


def _emit(message: str, callback: LogCallback | None) -> None:
    print(message)
    if callback is not None:
        callback(message)


def _extract_episode_metadata(ep: RssEpisode) -> tuple[float | None, datetime | None, str]:
    source: str | None = ep.content
    assert isinstance(source, str), "No source URL in episode"
    return ep.duration, ep.pub_date, source


def _youtube_metadata_from_source(source: str) -> tuple[float | None, datetime | None]:
    youtube_match = YOUTUBE_VIDEO_REGEX.match(source)
    if youtube_match is None:
        return None, None
    vid_id = youtube_match.group(4)
    if not vid_id:
        return None, None
    youtube_info = get_video_info(vid_id)
    assert youtube_info is not None, "Failed to fetch YouTube video info"
    return youtube_info.duration, youtube_info.upload_date


def _load_local_duration_and_date(
    bucket: str, prefix: Path, fallback_date: datetime | None
) -> tuple[float, datetime | None]:
    with tempfile.TemporaryDirectory() as temp_dir:
        suffix = prefix.suffix
        staging_file = Path(temp_dir) / f"temp_audio{suffix}"
        download_file(bucket, prefix.as_posix(), staging_file)
        duration = get_duration(staging_file)
        return duration, fallback_date


def _get_metadata(ep: RssEpisode, bucket: str, prefix: Path) -> MediaMetadata | None:
    try:
        return _build_metadata(ep, bucket, prefix)
    except Exception as exc:
        print(f"ERROR: _get_metadata: Failed to get metadata for {bucket}: {exc}")
        return None


def _build_metadata(ep: RssEpisode, bucket: str, prefix: Path) -> MediaMetadata:
    duration, upload_date, source = _extract_episode_metadata(ep)
    yt_duration, yt_upload_date = _youtube_metadata_from_source(source)
    duration = yt_duration if yt_duration is not None else duration
    upload_date = yt_upload_date if yt_upload_date is not None else upload_date

    missing_metadata = not isinstance(duration, float) or not isinstance(upload_date, datetime)
    if missing_metadata:
        duration, upload_date = _load_local_duration_and_date(bucket, prefix, ep.pub_date)

    assert isinstance(duration, float), "Incomplete metadata extracted"
    assert isinstance(upload_date, datetime), "Incomplete metadata extracted"

    return MediaMetadata(duration=duration, upload_date=upload_date, source=source, uploader=DEVICE)


def _download_youtube(vid_id: str, title: str, dest: Path) -> tuple[Path, bool]:
    url = f"https://www.youtube.com/watch?v={vid_id}"

    with tqdm(desc=f"↓ Downloading {title}", total=1) as progress:
        staging_file = download_video(url, dest, get_callback(progress))
        assert staging_file is not None, f"Failed to download: {url}"
        progress.set_description(f"✓ Downloaded {title}")

    sponsors_removed = False
    if (segments := fetch_sponsor_segments(vid_id)) and len(segments) > 0:
        with tqdm(desc=f"↘ Removing sponsors: {title}", total=len(segments)) as p_bar:
            remove_sponsors(staging_file, vid_id, get_callback(p_bar))
            sponsors_removed = True

    return staging_file, sponsors_removed


def _download_source_episode(content: str, title: str, dest: Path) -> tuple[Path, bool]:
    if youtube_match := YOUTUBE_VIDEO_REGEX.match(content):
        vid_id = youtube_match.group(4)
        return _download_youtube(vid_id, title, dest)
    return download_direct(content, dest)


def _upload_episode_file(
    stage: Path,
    episode_title: str,
    destination: tuple[str, str],
    metadata: MediaMetadata | None,
) -> None:
    bucket, key = destination
    with tqdm(desc=f"↑ Uploading {episode_title}", total=1) as progress:
        upload_file(
            bucket,
            key,
            stage,
            {"metadata": metadata, "callback": get_callback(progress)},
        )
        print(f"Uploaded episode to {bucket}/{key}")


def _download_episode(
    config: PodcastConfig, episode: RssEpisode, bucket: str, prefix: Path
) -> bool:
    file_title = normalize_title(config.name, episode.title)
    file_path = prefix / file_title
    if exists(bucket, file_path.as_posix()):
        return False

    with tempfile.TemporaryDirectory() as temp:
        stage, sponsored = _download_source_episode(episode.content, episode.title, Path(temp))
        stage = convert_to_opus(stage)

        metadata = _get_metadata(episode, bucket, file_path)
        if sponsored and metadata is not None:
            metadata.sponsors_removed = True
            print(f"Sponsors removed for episode: {episode.title}")

        key = file_path.with_suffix(stage.suffix).as_posix()
        _upload_episode_file(stage, episode.title, (bucket, key), metadata)

    return True


def _get_download_context(config: PodcastConfig) -> _DownloadContext:
    upload_path = Path(config.path)
    return _DownloadContext(
        config=config,
        bucket=upload_path.parts[1],
        prefix=Path(*upload_path.parts[2:]),
    )


def _collect_reference_episodes(config: PodcastConfig) -> list[RssEpisode]:
    if not config.references:
        return []
    with tqdm(desc=f"⟳ {config.name}: RSS feeds", total=1) as p_bar:
        references = process_feeds(config, get_callback(p_bar))
        p_bar.set_description(f"✓ {config.name}: {len(references)} reference episodes")
        return references


def _collect_download_episodes(config: PodcastConfig) -> list[RssEpisode]:
    with tqdm(desc=f"⟳ {config.name}: fetching episodes", total=1) as p_bar:
        downloads = process_sources(config, get_callback(p_bar))
        p_bar.set_description(f"✓ {config.name}: {len(downloads)} episodes")
        return downloads


def _align_download_episodes(
    config: PodcastConfig, references: list[RssEpisode], downloads: list[RssEpisode]
) -> list[RssEpisode]:
    if not references:
        return downloads
    pairs = align_episodes(references, downloads, config.name)
    episodes = [downloads[d_idx] for _, d_idx in pairs]
    print(f"Aligned to {len(episodes)} episodes for {config.name}")
    return episodes


def _apply_spacing_delay(episode: RssEpisode, remaining: int) -> None:
    if remaining <= 0 or not YOUTUBE_VIDEO_REGEX.match(episode.content or ""):
        return
    delay = random.randint(30, 120)
    for _ in tqdm(range(delay), desc="⏳ Spacing downloads", unit="s", leave=False):
        time.sleep(1)


def _download_episode_with_guard(
    context: _DownloadContext,
    episode: RssEpisode,
) -> tuple[bool, bool]:
    try:
        return _download_episode(context.config, episode, context.bucket, context.prefix), False
    except BotDetectionError as exc:
        print(f"ERROR: Bot detected for {context.config.name}, stopping series: {exc}")
        return False, True
    except Exception as exc:
        print(f"ERROR: Error downloading episode {episode.title}: {exc}")
        return False, False


def _download_episode_loop(
    context: _DownloadContext,
    episodes: list[RssEpisode],
    budget: int | None,
) -> int:
    downloaded = 0
    for idx, episode in enumerate(tqdm(episodes, desc=f"↓ Downloading {context.config.name}")):
        if budget is not None and downloaded >= budget:
            break

        remaining = len(episodes) - idx - 1
        downloaded_delta, stop_series = _process_episode_download(context, episode, remaining)
        if stop_series:
            break
        downloaded += downloaded_delta
    return downloaded


def _process_episode_download(
    context: _DownloadContext,
    episode: RssEpisode,
    remaining: int,
) -> tuple[int, bool]:
    did_download, stop_series = _download_episode_with_guard(context, episode)
    if stop_series:
        return 0, True
    if not did_download:
        return 0, False
    _apply_spacing_delay(episode, remaining)
    return 1, False


def download_series(config: PodcastConfig, budget: int | None = None) -> int:
    if not config.downloads:
        return 0

    context = _get_download_context(config)
    references = _collect_reference_episodes(config)
    downloads = _collect_download_episodes(config)
    episodes = _align_download_episodes(config, references, downloads)

    shuffle(episodes)
    return _download_episode_loop(context, episodes, budget)


def _upload_feed(
    channel: RssChannel, episodes: list[RssEpisode], bucket: str, key: str
) -> str | None:
    key = (Path(key) / "feed.rss").as_posix()
    rss: str = podcast_to_rss(channel, episodes)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "feed.rss"
        with open(temp_path, "w", encoding="utf-8") as temp_file:
            temp_file.write(rss)
        return upload_file(bucket, key, temp_path)


def _collect_series_feed_data(config: PodcastConfig) -> tuple[RssChannel, list[RssEpisode]]:
    with tqdm(desc=f"⟳ Collecting {config.name} episodes", total=1) as progress:
        channel: RssChannel = process_channel(config)
        episodes: list[RssEpisode] = process_feeds(config, get_callback(progress))
        progress.set_description(f"✓ Processed {config.name} feed")
    return channel, episodes


def _load_series_audio_files(bucket: str, prefix: str) -> list[str]:
    return [f for f in get_s3_files(bucket, prefix) if is_audio(f)]


def _apply_series_matches(
    episodes: list[RssEpisode], files: list[str], matches: list[tuple[int, int]]
) -> list[RssEpisode]:
    rss_episodes: list[RssEpisode] = []
    for file_idx, episode_idx in matches:
        episodes[episode_idx].content = files[file_idx]
        rss_episodes.append(episodes[episode_idx])
    return rss_episodes


def _match_series_episodes(
    config: PodcastConfig,
    bucket: str,
    prefix: str,
    episodes: list[RssEpisode],
) -> list[RssEpisode]:
    with tqdm(desc="↓ Fetching audio files", total=1) as progress:
        files = _load_series_audio_files(bucket, prefix)
        file_names = [Path(f).name for f in files]
        episode_names = [ep.title for ep in episodes]
        progress.set_description("* Matching episodes")

        matches = match(file_names, episode_names, config.name, get_callback(progress))
        rss_episodes = _apply_series_matches(episodes, files, matches)

        progress.set_description("✓ Uploaded RSS feed")
        return rss_episodes


def update_series(config: PodcastConfig) -> None:
    path = Path(config.path)
    bucket = path.parts[1]
    prefix = Path(*path.parts[2:]).as_posix()

    channel, episodes = _collect_series_feed_data(config)
    rss_episodes = _match_series_episodes(config, bucket, prefix, episodes)
    _upload_feed(channel, rss_episodes, bucket, prefix)


DEFAULT_DOWNLOAD_SERIES = download_series
DEFAULT_UPDATE_SERIES = update_series


@contextmanager
def _runtime_context(workdir: Path | None):
    original_cwd = Path.cwd()
    original_bot_detection = yt_downloader.PROPAGATE_BOT_DETECTION
    yt_downloader.PROPAGATE_BOT_DETECTION = True
    try:
        if workdir is not None:
            os.chdir(workdir)
        yield
    finally:
        os.chdir(original_cwd)
        yt_downloader.PROPAGATE_BOT_DETECTION = original_bot_detection


def _resolve_functions(
    download_series_fn: Callable[..., int] | None,
    update_series_fn: Callable[[PodcastConfig], None] | None,
) -> tuple[Callable[..., int], Callable[[PodcastConfig], None]]:
    download_func = download_series_fn or DEFAULT_DOWNLOAD_SERIES
    update_func = update_series_fn or DEFAULT_UPDATE_SERIES
    return download_func, update_func


def _load_configs(request: DownloadRunRequest) -> list[PodcastConfig]:
    configs: list[PodcastConfig] = load_podcasts_config(include=request.include)
    return [ensure_podcast_config(config) for config in configs]


def _budget_exhausted(state: _PipelineState) -> bool:
    return state.remaining is not None and state.remaining <= 0


def _record_download_failure(
    state: _PipelineState,
    config: PodcastConfig,
    exc: Exception,
    callback: LogCallback | None,
) -> None:
    if isinstance(exc, BotDetectionError):
        state.bot_detected = True
    state.failed_series.append(FailedSeries(config.name, "download", str(exc)))
    _emit(f"ERROR: Failed to download series {config.name}: {exc}", callback)


def _apply_download_result(
    state: _PipelineState,
    config: PodcastConfig,
    downloaded: int,
    callback: LogCallback | None,
) -> None:
    _emit(f"Successfully downloaded series: {config.name} ({downloaded} new)", callback)
    state.total_downloaded += downloaded
    if state.remaining is not None:
        state.remaining -= downloaded


def _run_download_phase(
    config: PodcastConfig,
    request: DownloadRunRequest,
    state: _PipelineState,
    download_func: Callable[..., int],
) -> bool:
    if request.skip_download:
        return True
    if _budget_exhausted(state):
        _emit("Download budget exhausted; skipping remaining series.", request.log_callback)
        return False

    _emit(f"Downloading series: {config.name}", request.log_callback)
    try:
        downloaded = download_func(config, budget=state.remaining)
    except Exception as exc:
        _record_download_failure(state, config, exc, request.log_callback)
        return True

    _apply_download_result(state, config, downloaded, request.log_callback)
    return True


def _run_update_phase(
    config: PodcastConfig,
    request: DownloadRunRequest,
    state: _PipelineState,
    update_func: Callable[[PodcastConfig], None],
) -> None:
    if request.skip_update:
        return
    try:
        _emit(f"Updating series: {config.name}", request.log_callback)
        update_func(config)
        _emit(f"Successfully updated series: {config.name}", request.log_callback)
    except Exception as exc:
        state.failed_series.append(FailedSeries(config.name, "update", str(exc)))
        _emit(f"ERROR: Failed to update series {config.name}: {exc}", request.log_callback)


def run_download_pipeline(
    request: DownloadRunRequest,
    *,
    download_series_fn: Callable[..., int] | None = None,
    update_series_fn: Callable[[PodcastConfig], None] | None = None,
) -> DownloadRunResult:
    download_func, update_func = _resolve_functions(download_series_fn, update_series_fn)

    with _runtime_context(request.workdir):
        configs = _load_configs(request)
        _emit(f"Processing {len(configs)} podcast(s)", request.log_callback)

        state = _PipelineState(remaining=request.max_downloads)
        for config in configs:
            if not _run_download_phase(config, request, state, download_func):
                break
            _run_update_phase(config, request, state, update_func)

    return DownloadRunResult(
        total_series=len(configs),
        total_episodes_downloaded=state.total_downloaded,
        failed_series=state.failed_series,
        bot_detected=state.bot_detected,
    )
