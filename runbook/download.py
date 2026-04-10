# ruff: noqa: E402

import argparse
import sys
import time
from pathlib import Path

import dotenv
from tqdm import tqdm

PROJECT_ROOT = Path(dotenv.find_dotenv()).parent

sys.path.insert(0, PROJECT_ROOT.as_posix())
dotenv.load_dotenv()

from src.orchestration import DownloadRunRequest, run_download_pipeline
from src.orchestration.download_service import download_series, update_series

DF_TARGETS = ["config/*.toml"]
DEFAULT_BOT_COOLDOWN = 15 * 60  # 15 minutes


def _bot_cooldown(seconds: int) -> None:
    print(f"Bot detection triggered — cooling down for {seconds // 60}m before exit.")
    try:
        for _ in tqdm(range(seconds, 0, -1), desc="⏳ Cooldown", unit="s", leave=True):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nCooldown interrupted.")


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
    parser.add_argument(
        "--bot-cooldown",
        type=int,
        default=DEFAULT_BOT_COOLDOWN,
        metavar="SECONDS",
        help=f"Seconds to wait after bot detection (default: {DEFAULT_BOT_COOLDOWN}s)",
    )
    args = parser.parse_args()
    result = run_download_pipeline(
        DownloadRunRequest(
            include=args.include,
            skip_download=args.skip_download,
            skip_update=args.skip_update,
            max_downloads=args.max_downloads,
            workdir=PROJECT_ROOT,
        ),
        download_series_fn=download_series,
        update_series_fn=update_series,
    )
    if result.bot_detected:
        _bot_cooldown(args.bot_cooldown)
        sys.exit(1)


if __name__ == "__main__":
    main()
    sys.exit(0)
