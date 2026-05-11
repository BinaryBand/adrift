import random
import sys
import time
from typing import Annotated

import dotenv
import typer

from src.application.context import AppContext
from src.application.download import (
    DownloadPipeline,
    DownloadPipelineDeps,
    DownloadPipelineRuntime,
    DownloadRunOptions,
)

DF_TARGETS = ["config/*.toml"]
DEFAULT_MAX_DOWNLOADS = 10
DEFAULT_BOT_COOLDOWN = 60 * 60  # 1 hour


def _run(
    include: Annotated[list[str], typer.Option(help="Config files to include")] = DF_TARGETS,
    skip_schedule_filter: Annotated[
        bool, typer.Option(help="Include configs even when their schedule does not match today.")
    ] = False,
    tags: Annotated[
        list[str],
        typer.Option(help="Tag(s) or podcast names to limit downloads to"),
    ] = [],
    skip_download: Annotated[
        bool, typer.Option(help="Skip download/upload stage (only enrich and update RSS).")
    ] = False,
    skip_update: Annotated[bool, typer.Option(help="Skip RSS feed update stage.")] = False,
    max_downloads: Annotated[
        int, typer.Option(help="Max number of episodes to download per run.")
    ] = DEFAULT_MAX_DOWNLOADS,
    bot_cooldown: Annotated[
        int, typer.Option(help="Seconds to wait before exiting after bot detection.")
    ] = DEFAULT_BOT_COOLDOWN,
    refresh_sources: Annotated[
        bool, typer.Option(help="Bypass fresh source caches and refetch source data.")
    ] = False,
) -> None:
    dotenv.load_dotenv()
    ctx = AppContext.from_env()

    from src.app_common import filter_podcasts_by_tags, load_podcasts_config
    from src.catalog import MergeConfigOptions, merge_config
    from src.orchestration.download_enrich import enrich_with_sponsors
    from src.orchestration.download_process import build_download_queue, download_and_upload
    from src.orchestration.download_rss import update_rss
    from src.utils.run_ui import build_merge_callbacks, create_run_ui
    from src.youtube.downloader import BotDetectionError

    configs = load_podcasts_config(
        include=include,
        skip_schedule_filter=skip_schedule_filter,
    )

    configs = filter_podcasts_by_tags(configs, tags)

    pipeline_options = DownloadRunOptions(
        skip_download=skip_download,
        skip_update=skip_update,
        max_downloads=max_downloads,
        refresh_sources=refresh_sources,
    )

    try:
        with create_run_ui(len(configs), "Downloading") as ui, ui.output_context():
            runtime = DownloadPipelineRuntime(ctx=ctx, ui=ui, options=pipeline_options)
            deps = DownloadPipelineDeps(
                merge_config=merge_config,
                merge_options_factory=lambda refresh, on_stage, callback: MergeConfigOptions(
                    refresh_sources=refresh,
                    on_stage=on_stage,
                    callback=callback,
                ),
                enrich_with_sponsors=enrich_with_sponsors,
                build_download_queue=build_download_queue,
                download_and_upload=download_and_upload,
                update_rss=update_rss,
                build_merge_callbacks=build_merge_callbacks,
                bot_detection_error=BotDetectionError,
            )
            downloaded_total = DownloadPipeline(runtime, deps).run(configs).value

    except BotDetectionError:
        sys.stderr.write(f"\nBot detection triggered — cooling down for {bot_cooldown}s\n")
        jitter = bot_cooldown * 0.1
        bot_cooldown += int((random.random() - 0.5) * jitter)  # Add up to ±10% random jitter
        time.sleep(bot_cooldown)
        sys.exit(1)

    sys.stderr.write(f"\nDownloaded {downloaded_total} new episode(s).\n")


def main() -> None:
    typer.run(_run)


if __name__ == "__main__":
    main()
