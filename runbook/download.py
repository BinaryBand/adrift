# ruff: noqa: E402

import argparse
import random
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from random import shuffle

import dotenv
from tqdm import tqdm

sys.path.insert(0, Path(dotenv.find_dotenv()).parent.as_posix())
dotenv.load_dotenv()

import src.youtube.downloader as yt_downloader
from src.app_common import PodcastConfig, ensure_podcast_config, load_podcasts_config
from src.app_runner import get_s3_files, normalize_title
from src.catalog import (
    align_episodes,
    match,
    process_channel,
    process_feeds,
    process_sources,
)
from src.files.audio import convert_to_opus, get_duration, is_audio
from src.files.s3 import download_file, exists, upload_file
from src.models import DEVICE, MediaMetadata
from src.utils.progress import get_callback
from src.utils.regex import YOUTUBE_VIDEO_REGEX
from src.web.rss import RssChannel, RssEpisode, download_direct, podcast_to_rss
from src.web.sponsorblock import fetch_sponsor_segments, remove_sponsors
from src.youtube.downloader import BotDetectionError, download_video
from src.youtube.metadata import get_video_info

# Ask the YouTube downloader to propagate bot-detection errors so this
# runbook can stop further YouTube downloads when detection occurs.
yt_downloader.PROPAGATE_BOT_DETECTION = True


DF_TARGETS = ["config/*.toml"]


# ---------------------------------------------------------------------------
# Download phase helpers
# ---------------------------------------------------------------------------


def _get_metadata(ep: RssEpisode, bucket: str, prefix: Path) -> MediaMetadata | None:
    try:
        duration: float | None = ep.duration
        upload_date: datetime | None = ep.pub_date
        source: str | None = ep.content
        assert isinstance(source, str), "No source URL in episode"

        youtube_match = YOUTUBE_VIDEO_REGEX.match(source)
        if youtube_match and (vid_id := youtube_match.group(4)):
            youtube_info = get_video_info(vid_id)
            assert youtube_info is not None, "Failed to fetch YouTube video info"

            duration = youtube_info.duration
            upload_date = youtube_info.upload_date

        if not isinstance(duration, float) or not isinstance(upload_date, datetime):
            with tempfile.TemporaryDirectory() as temp_dir:
                suffix = prefix.suffix
                staging_file = Path(temp_dir) / f"temp_audio{suffix}"
                download_file(bucket, prefix.as_posix(), staging_file)

                duration = get_duration(staging_file)
                upload_date = ep.pub_date

        assert isinstance(duration, float), "Incomplete metadata extracted"
        assert isinstance(upload_date, datetime), "Incomplete metadata extracted"

        return MediaMetadata(
            duration=duration, upload_date=upload_date, source=source, uploader=DEVICE
        )

    except Exception as e:
        print(f"ERROR: _get_metadata: Failed to get metadata for {bucket}: {e}")
        return None


def _download_youtube(vid_id: str, title: str, dest: Path) -> tuple[Path, bool]:
    """Download from YouTube."""
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


def _download_episode(
    config: PodcastConfig, episode: RssEpisode, bucket: str, prefix: Path
) -> bool:
    """Download an episode if not already on S3. Returns True if a new file was uploaded."""
    file_title = normalize_title(config.name, episode.title)
    file_path = prefix / file_title

    if not exists(bucket, file_path.as_posix()):
        with tempfile.TemporaryDirectory() as temp:
            dest, sponsored = Path(temp), False

            if youtube_match := YOUTUBE_VIDEO_REGEX.match(episode.content):
                vid_id = youtube_match.group(4)
                stage, sponsored = _download_youtube(vid_id, episode.title, dest)
            else:
                stage, sponsored = download_direct(episode.content, dest)

            stage = convert_to_opus(stage)

            metadata = _get_metadata(episode, bucket, file_path)
            if sponsored and metadata is not None:
                metadata.sponsors_removed = True
                print(f"Sponsors removed for episode: {episode.title}")

            key = file_path.with_suffix(stage.suffix).as_posix()
            with tqdm(desc=f"↑ Uploading {episode.title}", total=1) as progress:
                upload_file(
                    bucket,
                    key,
                    stage,
                    {"metadata": metadata, "callback": get_callback(progress)},
                )
                print(f"Uploaded episode to {bucket}/{key}")
        return True

    return False


def _download_series(config: PodcastConfig, budget: int | None = None) -> int:
    """Download episodes for a podcast series.

    Args:
        budget: Maximum number of new downloads; None means unlimited.

    Returns:
        Number of episodes actually downloaded.
    """
    upload_path = Path(config.path)
    bucket = upload_path.parts[1]
    prefix = Path(*upload_path.parts[2:])

    if not config.downloads:
        return 0

    # Phase 1: RSS reference feeds (only when configured)
    references: list[RssEpisode] = []
    if config.references:
        with tqdm(desc=f"⟳ {config.name}: RSS feeds", total=1) as p_bar:
            references = process_feeds(config, get_callback(p_bar))
            p_bar.set_description(f"✓ {config.name}: {len(references)} reference episodes")

    # Phase 2: Download sources (YouTube, direct links, etc.)
    with tqdm(desc=f"⟳ {config.name}: fetching episodes", total=1) as p_bar:
        downloads = process_sources(config, get_callback(p_bar))
        p_bar.set_description(f"✓ {config.name}: {len(downloads)} episodes")

    # Phase 3: Align and filter
    if references:
        pairs = align_episodes(references, downloads, config.name)
        episodes = [downloads[d_idx] for _, d_idx in pairs]
        print(f"Aligned to {len(episodes)} episodes for {config.name}")
    else:
        episodes = downloads

    shuffle(episodes)
    downloaded = 0
    for i, ep in enumerate(tqdm(episodes, desc=f"↓ Downloading {config.name}")):
        if budget is not None and downloaded >= budget:
            break
        try:
            did_download = _download_episode(config, ep, bucket, prefix)
        except BotDetectionError as e:
            print(f"ERROR: Bot detected for {config.name}, stopping series: {e}")
            break
        except Exception as e:
            print(f"ERROR: Error downloading episode {ep.title}: {e}")
            continue

        if did_download:
            downloaded += 1
            remaining = len(episodes) - i - 1
            if remaining > 0 and YOUTUBE_VIDEO_REGEX.match(ep.content or ""):
                delay = random.randint(30, 120)
                for _ in tqdm(range(delay), desc="⏳ Spacing downloads", unit="s", leave=False):
                    time.sleep(1)

    return downloaded


# ---------------------------------------------------------------------------
# Update (RSS feed rebuild) phase helpers
# ---------------------------------------------------------------------------


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


def _update_series(config: PodcastConfig) -> None:
    """Rebuild the RSS feed for a podcast series."""
    path = Path(config.path)
    bucket = path.parts[1]
    prefix = Path(*path.parts[2:]).as_posix()

    with tqdm(desc=f"⟳ Collecting {config.name} episodes", total=1) as progress:
        channel: RssChannel = process_channel(config)
        episodes: list[RssEpisode] = process_feeds(config, get_callback(progress))
        progress.set_description(f"✓ Processed {config.name} feed")

    with tqdm(desc="↓ Fetching audio files", total=1) as progress:
        files = [f for f in get_s3_files(bucket, prefix) if is_audio(f)]
        file_names = [Path(f).name for f in files]
        episode_names = [ep.title for ep in episodes]
        progress.set_description("* Matching episodes")

        matches = match(file_names, episode_names, config.name, get_callback(progress))
        rss_episodes: list[RssEpisode] = []
        for f_idx, e_idx in matches:
            episodes[e_idx].content = files[f_idx]
            rss_episodes.append(episodes[e_idx])

        _upload_feed(channel, rss_episodes, bucket, prefix)
        progress.set_description("✓ Uploaded RSS feed")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and update podcasts.")
    parser.add_argument("--include", nargs="*", default=DF_TARGETS, help="Config files to include")
    parser.add_argument("--skip-download", action="store_true", default=False)
    parser.add_argument("--skip-update", action="store_true", default=False)
    parser.add_argument(
        "--max-downloads",
        type=int,
        default=None,
        metavar="N",
        help="Maximum total number of new episode downloads across all series (default: unlimited)",
    )
    args = parser.parse_args()

    configs: list[PodcastConfig] = load_podcasts_config(include=args.include)
    # Coerce any legacy dict entries to canonical `PodcastConfig`
    configs = [ensure_podcast_config(c) for c in configs]
    print(f"Processing {len(configs)} podcast(s)")

    remaining = args.max_downloads
    for config in configs:
        if not args.skip_download:
            if remaining is not None and remaining <= 0:
                print("Download budget exhausted; skipping remaining series.")
                break
            try:
                print(f"Downloading series: {config.name}")
                n = _download_series(config, budget=remaining)
                print(f"Successfully downloaded series: {config.name} ({n} new)")
                if remaining is not None:
                    remaining -= n
            except Exception as e:
                print(f"ERROR: Failed to download series {config.name}: {e}")

        if not args.skip_update:
            try:
                print(f"Updating series: {config.name}")
                _update_series(config)
                print(f"Successfully updated series: {config.name}")
            except Exception as e:
                print(f"ERROR: Failed to update series {config.name}: {e}")


if __name__ == "__main__":
    main()
    sys.exit(0)
