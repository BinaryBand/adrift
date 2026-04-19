import sys
import time
from typing import Annotated

import dotenv
import typer

DF_TARGETS = ["config/*.toml"]
DEFAULT_MAX_DOWNLOADS = 10
DEFAULT_BOT_COOLDOWN = 300


def _run(
    include: Annotated[list[str], typer.Option(help="Config files to include")] = DF_TARGETS,
    skip_schedule_filter: Annotated[
        bool, typer.Option(help="Include configs even when their schedule does not match today.")
    ] = False,
    skip_download: Annotated[
        bool, typer.Option(help="Skip download/upload stage (only enrich and update RSS).")
    ] = False,
    skip_update: Annotated[bool, typer.Option(help="Skip RSS feed update stage.")] = False,
    max_downloads: Annotated[
        int, typer.Option(help="Maximum number of episodes to download per run.")
    ] = DEFAULT_MAX_DOWNLOADS,
    bot_cooldown: Annotated[
        int, typer.Option(help="Seconds to wait before exiting after bot detection.")
    ] = DEFAULT_BOT_COOLDOWN,
    refresh_sources: Annotated[
        bool, typer.Option(help="Bypass fresh source caches and refetch source data.")
    ] = False,
) -> None:
    dotenv.load_dotenv()

    from src.app_common import load_podcasts_config
    from src.catalog import merge_config
    from src.orchestration.download_service import (
        download_and_upload,
        enrich_with_sponsors,
        update_rss,
    )
    from src.utils.run_ui import build_merge_callbacks, create_run_ui
    from src.youtube.downloader import BotDetectionError

    configs = load_podcasts_config(
        include=include,
        skip_schedule_filter=skip_schedule_filter,
    )

    downloaded_total = 0

    try:
        with create_run_ui(len(configs), "Downloading") as ui, ui.output_context():
            on_stage, callback = build_merge_callbacks(ui)
            for config in configs:
                ui.set_podcast(config.name)

                ui.set_stage("merge")
                result = merge_config(
                    config,
                    refresh_sources=refresh_sources,
                    on_stage=on_stage,
                    callback=callback,
                )

                ui.set_stage("enrich")
                episodes = enrich_with_sponsors(result)

                if not skip_download:
                    ui.set_stage("download")
                    budget = max(0, max_downloads - downloaded_total)
                    for ep in episodes[:budget]:
                        try:
                            newly_uploaded = download_and_upload(ep, config)
                            if newly_uploaded:
                                downloaded_total += 1
                        except BotDetectionError:
                            raise
                        except Exception as exc:
                            ui.emit("error", f"{config.name} — {ep.episode.title}: {exc}")

                if not skip_update:
                    ui.set_stage("rss")
                    update_rss(config)

                ui.set_stage("done")
                ui.advance()

    except BotDetectionError:
        sys.stderr.write(f"\nBot detection triggered — cooling down for {bot_cooldown}s\n")
        time.sleep(bot_cooldown)
        sys.exit(1)

    sys.stderr.write(f"\nDownloaded {downloaded_total} new episode(s).\n")


def main() -> None:
    typer.run(_run)


if __name__ == "__main__":
    main()
