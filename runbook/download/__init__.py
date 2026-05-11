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


def _normalize_cli_inputs(
    include: list[str] | None,
    tags: list[str] | None,
) -> tuple[list[str], list[str]]:
    return (include or DF_TARGETS, tags or [])


def _load_configs(
    include: list[str],
    skip_schedule_filter: bool,
    tags: list[str],
):
    from src.app_common import filter_podcasts_by_tags, load_podcasts_config

    configs = load_podcasts_config(
        include=include,
        skip_schedule_filter=skip_schedule_filter,
    )
    return filter_podcasts_by_tags(configs, tags)


def _build_pipeline(
    ctx: AppContext,
    ui,
    pipeline_options: DownloadRunOptions,
) -> DownloadPipeline:
    from src.catalog import MergeConfigOptions, merge_config
    from src.orchestration.download_enrich import enrich_with_sponsors
    from src.orchestration.download_process import build_download_queue, download_and_upload
    from src.orchestration.download_rss import update_rss
    from src.utils.run_ui import build_merge_callbacks
    from src.youtube.downloader import BotDetectionError

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
    return DownloadPipeline(runtime, deps)


def _run_pipeline(
    configs,
    ctx: AppContext,
    pipeline_options: DownloadRunOptions,
) -> int:
    from src.utils.run_ui import create_run_ui

    with create_run_ui(len(configs), "Downloading") as ui, ui.output_context():
        pipeline = _build_pipeline(ctx, ui, pipeline_options)
        return int(pipeline.run(configs).value)


def _sleep_on_bot_detection(bot_cooldown: int) -> None:
    sys.stderr.write(f"\nBot detection triggered — cooling down for {bot_cooldown}s\n")
    jitter = bot_cooldown * 0.1
    wait_seconds = bot_cooldown + int((random.random() - 0.5) * jitter)
    time.sleep(wait_seconds)


def _build_pipeline_options(
    skip_download: bool,
    skip_update: bool,
    max_downloads: int,
    refresh_sources: bool,
) -> DownloadRunOptions:
    return DownloadRunOptions(
        skip_download=skip_download,
        skip_update=skip_update,
        max_downloads=max_downloads,
        refresh_sources=refresh_sources,
    )


def _run_with_bot_detection(
    configs,
    ctx: AppContext,
    pipeline_options: DownloadRunOptions,
    bot_cooldown: int,
) -> int:
    from src.youtube.downloader import BotDetectionError

    try:
        return _run_pipeline(configs, ctx, pipeline_options)
    except BotDetectionError:
        _sleep_on_bot_detection(bot_cooldown)
        raise typer.Exit(code=1)


def _run(
    include: Annotated[list[str] | None, typer.Option(help="Config files to include")] = None,
    skip_schedule_filter: Annotated[
        bool, typer.Option(help="Include configs even when their schedule does not match today.")
    ] = False,
    tags: Annotated[
        list[str] | None,
        typer.Option(help="Tag(s) or podcast names to limit downloads to"),
    ] = None,
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

    include, tags = _normalize_cli_inputs(include, tags)

    configs = _load_configs(include, skip_schedule_filter, tags)

    pipeline_options = _build_pipeline_options(
        skip_download,
        skip_update,
        max_downloads,
        refresh_sources,
    )

    downloaded_total = _run_with_bot_detection(configs, ctx, pipeline_options, bot_cooldown)

    sys.stderr.write(f"\nDownloaded {downloaded_total} new episode(s).\n")


app = typer.Typer(add_completion=False)
app.command()(_run)


def main() -> None:
    app(standalone_mode=False)


if __name__ == "__main__":
    main()
