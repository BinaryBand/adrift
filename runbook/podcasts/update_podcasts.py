from pathlib import Path
from tqdm import tqdm

import tempfile
import argparse
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from runbook.podcasts.download_podcasts import DF_TARGETS
from src.app_common import PodcastData, load_podcasts_config
from src.app_runner import get_s3_files
from src.catalog import match, process_channel, process_feeds
from src.files.audio import is_audio
from src.files.s3 import upload_file
from src.utils.progress import get_callback
from src.web.rss import RssChannel, RssEpisode, podcast_to_rss


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

    return None


def update_series(config: PodcastData) -> None:
    """Update a complete podcast series: download episodes and generate RSS feed."""
    title = config.title
    path = Path(config.path)
    bucket = path.parts[1]
    prefix = Path(*path.parts[2:]).as_posix()

    with tqdm(desc=f"⟳ Collecting {title} episodes", total=1) as progress:
        channel: RssChannel = process_channel(config)
        episodes: list[RssEpisode] = process_feeds(config, get_callback(progress))
        progress.set_description(f"✓ Processed {title} feed")

    with tqdm(desc="↓ Fetching audio files", total=1) as progress:
        files = [f for f in get_s3_files(bucket, prefix) if is_audio(f)]
        file_names = [Path(f).name for f in files]
        episode_names = [ep.title for ep in episodes]
        progress.set_description("* Matching episodes")

        matches = match(file_names, episode_names, title, get_callback(progress))
        rss_episodes = []
        for f_idx, e_idx in matches:
            episodes[e_idx].content = files[f_idx]
            rss_episodes.append(episodes[e_idx])

        _upload_feed(channel, rss_episodes, bucket, prefix)
        progress.set_description("✓ Uploaded RSS feed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Updating podcast feeds.")
    parser.add_argument("--include", nargs="+", type=str, default=DF_TARGETS)
    args = parser.parse_args()

    print("Updating podcast series based on configuration")
    configs: list[PodcastData] = load_podcasts_config(include=args.include)
    for config in configs:
        try:
            print(f"Updating series: {config.title}")
            update_series(config)
            print(f"Successfully updated series: {config.title}")
        except Exception as e:
            print(f"ERROR: Failed to update series for {config.title}: {e}")

    print("Series update process completed")
