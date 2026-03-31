from datetime import datetime
from random import shuffle
from pathlib import Path
from tqdm import tqdm

import tempfile
import argparse
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.app_common import PodcastConfig, PodcastData, load_podcasts_config
from src.app_runner import normalize_title
from src.catalog import process_sources
from src.files.audio import get_duration
from src.files.s3 import exists, upload_file, download_file
from src.models import DEVICE, MediaMetadata
from src.utils.progress import get_callback
from src.utils.regex import YOUTUBE_VIDEO_REGEX
from src.web.rss import RssEpisode, download_direct
from src.web.sponsorblock import fetch_sponsor_segments, remove_sponsors
from src.youtube.downloader import BotDetectionError, download_video
import src.youtube.downloader as yt_downloader

# Ask the YouTube downloader to propagate bot-detection errors so this
# runbook can stop further YouTube downloads when detection occurs.
yt_downloader.PROPAGATE_BOT_DETECTION = True
from src.youtube.metadata import get_video_info


# DF_TARGETS originally referenced JSON files; migrate to TOML-only.
# DF_TARGETS = ["config/youtube.json", "config/.podcasts.json"]
DF_TARGETS = ["config/podcasts.toml", "config/youtube.toml"]
YOUTUBE_BOT_DETECTED = False


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
):
    file_title = normalize_title(config.title, episode.title)
    file_path = prefix / file_title

    if not exists(bucket, file_path.as_posix()):
        with tempfile.TemporaryDirectory() as temp:
            dest, sponsored = Path(temp), False

            if youtube_match := YOUTUBE_VIDEO_REGEX.match(episode.content):
                vid_id = youtube_match.group(4)
                global YOUTUBE_BOT_DETECTED
                if YOUTUBE_BOT_DETECTED:
                    print(f"WARNING: Skipping due to bot detection: {episode.title}")
                    return

                try:
                    stage, sponsored = _download_youtube(vid_id, episode.title, dest)
                except BotDetectionError as e:
                    # Mark global flag so subsequent episodes skip YouTube
                    YOUTUBE_BOT_DETECTED = True
                    print(f"ERROR: Bot detected, skipping YouTube downloads: {e}")
                    return
            else:
                stage, sponsored = download_direct(episode.content, dest)

            metadata = _get_metadata(episode, bucket, file_path)
            if sponsored and metadata is not None:
                metadata.sponsors_removed = True
                print(f"Sponsors removed for episode: {episode.title}")

            key = file_path.with_suffix(stage.suffix).as_posix()
            with tqdm(desc=f"↑ Uploading {episode.title}", total=1) as progress:
                upload_file(bucket, key, stage, metadata, get_callback(progress))
                print(f"Uploaded episode to {bucket}/{key}")


def _download_series(config: PodcastConfig, upload_path: Path) -> int:
    """Download all episodes from sources for a podcast series."""
    bucket = upload_path.parts[1]
    prefix = Path(*upload_path.parts[2:])

    episodes: list[RssEpisode] = []
    if config.downloads:
        with tqdm(desc=f"⟳ Finding {config.title} episodes", total=1) as p_bar:
            episodes = process_sources(config, get_callback(p_bar))
            p_bar.set_description(f"✓ Found {len(episodes)} episodes")

        shuffle(episodes)  # Randomize download order to improve parallelism
        for ep in tqdm(episodes, desc=f"↓ Downloading {config.title}"):
            try:
                _download_episode(config, ep, bucket, prefix)
            except Exception as e:
                print(f"ERROR: Error downloading episode {ep.title}: {e}")

    return len(episodes)


def update_series(config: PodcastConfig) -> None:
    """Update a complete podcast series: download episodes and generate RSS feed."""
    print(f"Downloading series: {config.title}")
    try:
        _download_series(config, Path(config.path))
        print(f"Successfully downloaded series: {config.title}")
    except Exception as e:
        print(f"ERROR: update_series: Failed to download series {config.title}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Downloading podcast files.")
    parser.add_argument("--include", nargs="+", type=str, default=DF_TARGETS)
    args = parser.parse_args()

    print("Downloading podcast series based on configuration")
    configs: list[PodcastConfig] = load_podcasts_config(include=args.include)
    for config in configs:
        update_series(config)

    print("Podcast download process completed.")
