"""Download CLI: fetch and upload podcast episodes."""

from __future__ import annotations

import random
import sys
import time
from typing import Annotated

import typer

from adrift.cli import (
    IncludeConfigsOption,
    SkipScheduleFilterOption,
    TagsOption,
    bootstrap_run_configs,
    build_cli,
)
from adrift.cli.composition import build_app_context
from adrift.core.models.podcast_config import PodcastConfig
from adrift.core.services.context import AppContext
from adrift.core.services.download import (
    DownloadPipeline,
    DownloadPipelineDeps,
    DownloadPipelineRuntime,
    DownloadRunOptions,
)
from adrift.core.util.run_ui import BaseRunUI

DEFAULT_MAX_DOWNLOADS = 10
DEFAULT_BOT_COOLDOWN = 60 * 60  # 1 hour


def _build_pipeline(
    ctx: AppContext,
    ui: BaseRunUI,
    pipeline_options: DownloadRunOptions,
) -> DownloadPipeline:
    from adrift.adapters.process.youtube.downloader import BotDetectionError  # noqa: PLC0415
    from adrift.core.services.catalog import MergeConfigOptions, merge_config  # noqa: PLC0415
    from adrift.core.services.download_enrich import enrich_with_sponsors  # noqa: PLC0415
    from adrift.core.services.download_process import (  # noqa: PLC0415
        build_download_queue,
        download_and_upload,
    )
    from adrift.core.services.download_rss import update_rss  # noqa: PLC0415
    from adrift.core.util.run_ui import build_merge_callbacks  # noqa: PLC0415

    # greedy one-to-one bipartite matching
    runtime = DownloadPipelineRuntime(ctx=ctx, ui=ui, options=pipeline_options)
    deps = DownloadPipelineDeps(
        merge_config=merge_config,
        merge_options_factory=lambda refresh, on_stage, callback: MergeConfigOptions(
            refresh_sources=refresh,
            on_stage=on_stage,
            callback=callback,
            episode_source_factory=ctx.episode_source_factory,
            alignment_provider=ctx.alignment_provider,
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
    configs: list[PodcastConfig],
    ctx: AppContext,
    pipeline_options: DownloadRunOptions,
) -> int:
    from adrift.core.util.run_ui import create_run_ui  # noqa: PLC0415

    with create_run_ui(len(configs), "Downloading") as ui, ui.output_context():
        pipeline = _build_pipeline(ctx, ui, pipeline_options)
        return int(pipeline.run(configs).value)


def _sleep_on_bot_detection(bot_cooldown: int) -> None:
    sys.stderr.write(f"\nBot detection triggered - cooling down for {bot_cooldown}s\n")
    jitter = bot_cooldown * 0.1
    wait_seconds = bot_cooldown + int((random.random() - 0.5) * jitter)  # noqa: S311
    time.sleep(wait_seconds)


def _build_pipeline_options(
    dry_run: bool,
    skip_download: bool,
    skip_update: bool,
    max_downloads: int,
    refresh_sources: bool,
) -> DownloadRunOptions:
    return DownloadRunOptions(
        skip_download=skip_download or dry_run,
        skip_update=skip_update or dry_run,
        max_downloads=max_downloads,
        refresh_sources=refresh_sources,
        show_download_plan=dry_run,
    )


def _run_with_bot_detection(
    configs: list[PodcastConfig],
    ctx: AppContext,
    pipeline_options: DownloadRunOptions,
    bot_cooldown: int,
) -> int:
    from adrift.adapters.process.youtube.downloader import BotDetectionError  # noqa: PLC0415

    try:
        return _run_pipeline(configs, ctx, pipeline_options)
    except BotDetectionError:
        _sleep_on_bot_detection(bot_cooldown)
        raise typer.Exit(code=1) from None


def _run(  # noqa: PLR0913
    include: IncludeConfigsOption = None,
    skip_schedule_filter: SkipScheduleFilterOption = False,
    tags: TagsOption = None,
    dry_run: bool = typer.Option(
        False,  # noqa: FBT003
        help="Simulate a download run without downloading/uploading media or updating RSS.",
    ),
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
    from adrift.adapters.process.alignment import ensure_rust_alignment_backend  # noqa: PLC0415

    ensure_rust_alignment_backend()

    configs, _ = bootstrap_run_configs(include, tags, skip_schedule_filter=skip_schedule_filter)
    ctx = build_app_context()
    pipeline_options = _build_pipeline_options(
        dry_run,
        skip_download,
        skip_update,
        max_downloads,
        refresh_sources,
    )

    downloaded_total = _run_with_bot_detection(configs, ctx, pipeline_options, bot_cooldown)

    if dry_run:
        sys.stderr.write("\nDry run complete. No downloads or RSS updates were performed.\n")
    else:
        sys.stderr.write(f"\nDownloaded {downloaded_total} new episode(s).\n")


app, main = build_cli(_run)


if __name__ == "__main__":
    main()
