import argparse
import sys
import time

import dotenv
from tqdm import tqdm

DF_TARGETS = ["config/*.toml"]
DEFAULT_MAX_DOWNLOADS = 10
DEFAULT_BOT_COOLDOWN = 300


def main() -> None:
    dotenv.load_dotenv()

    from src.app_common import load_podcasts_config
    from src.catalog import merge_config
    from src.orchestration.download_service import (
        download_and_upload,
        enrich_with_sponsors,
        update_rss,
    )
    from src.youtube.downloader import BotDetectionError

    parser = argparse.ArgumentParser(description="Download episodes, remove ads, and upload to S3.")
    parser.add_argument("--include", nargs="*", default=DF_TARGETS, help="Config files to include")
    parser.add_argument(
        "--skip-schedule-filter",
        action="store_true",
        default=False,
        help="Include configs even when their schedule does not match today.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        default=False,
        help="Skip download/upload stage (only enrich and update RSS).",
    )
    parser.add_argument(
        "--skip-update",
        action="store_true",
        default=False,
        help="Skip RSS feed update stage.",
    )
    parser.add_argument(
        "--max-downloads",
        type=int,
        default=DEFAULT_MAX_DOWNLOADS,
        help="Maximum number of episodes to download per run.",
    )
    parser.add_argument(
        "--bot-cooldown",
        type=int,
        default=DEFAULT_BOT_COOLDOWN,
        help="Seconds to wait before exiting after bot detection.",
    )
    parser.add_argument(
        "--refresh-sources",
        action="store_true",
        default=False,
        help="Bypass fresh source caches and refetch source data.",
    )
    args = parser.parse_args()

    configs = load_podcasts_config(
        include=args.include,
        skip_schedule_filter=args.skip_schedule_filter,
    )

    bar = tqdm(configs, desc="Downloading", unit="podcast", file=sys.stderr)
    downloaded_total = 0

    try:
        for config in bar:
            bar.set_description(config.name)

            bar.set_postfix_str("merge")
            result = merge_config(config, refresh_sources=args.refresh_sources)

            bar.set_postfix_str("enrich")
            episodes = enrich_with_sponsors(result)

            if not args.skip_download:
                bar.set_postfix_str("download")
                budget = max(0, args.max_downloads - downloaded_total)
                for ep in episodes[:budget]:
                    try:
                        newly_uploaded = download_and_upload(ep, config)
                        if newly_uploaded:
                            downloaded_total += 1
                    except BotDetectionError:
                        raise
                    except Exception as exc:
                        sys.stderr.write(f"ERROR: {config.name} — {ep.episode.title}: {exc}\n")

            if not args.skip_update:
                bar.set_postfix_str("rss")
                update_rss(config)

            bar.set_postfix_str("done")

    except BotDetectionError:
        sys.stderr.write(f"\nBot detection triggered — cooling down for {args.bot_cooldown}s\n")
        time.sleep(args.bot_cooldown)
        sys.exit(1)

    sys.stderr.write(f"\nDownloaded {downloaded_total} new episode(s).\n")


if __name__ == "__main__":
    main()
