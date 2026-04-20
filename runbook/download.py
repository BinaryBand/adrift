import sys
import time
from collections.abc import Callable
from typing import Annotated, Any, Protocol

import dotenv
import typer

from src.app_common import PodcastConfig
from src.models.pipeline import DownloadEpisode
from src.orchestration.download_service import DownloadProgressHooks, DownloadQueueItem

DF_TARGETS = ["config/*.toml"]
DEFAULT_MAX_DOWNLOADS = 10
DEFAULT_BOT_COOLDOWN = 300


class _DownloadUiPort(Protocol):
    def emit(self, level: Any, message: str) -> None: ...

    def set_operation(self, operation: str) -> None: ...

    def clear_operation(self) -> None: ...

    def operation_callback(self, current: int, total: int | None) -> None: ...


def _download_episodes(
    episodes: list[DownloadEpisode],
    config: PodcastConfig,
    *,
    downloaded_total: int,
    max_downloads: int,
    ui: _DownloadUiPort,
    build_download_queue: Callable[[list[DownloadEpisode], PodcastConfig], list[DownloadQueueItem]],
    download_and_upload: Callable[
        [DownloadEpisode, PodcastConfig, DownloadProgressHooks | None], bool
    ],
    bot_detection_error: type[BaseException],
) -> int:
    additional_downloads = 0
    for queue_item in build_download_queue(episodes, config):
        if downloaded_total + additional_downloads >= max_downloads:
            break
        if queue_item.exists_on_s3:
            continue
        try:
            progress_hooks = DownloadProgressHooks(
                on_operation=ui.set_operation,
                on_progress=ui.operation_callback,
                on_complete=ui.clear_operation,
            )
            newly_uploaded = download_and_upload(queue_item.episode, config, progress_hooks)
            if newly_uploaded:
                additional_downloads += 1
        except bot_detection_error:
            raise
        except Exception as exc:
            ui.clear_operation()
            ui.emit("error", f"{config.name} — {queue_item.episode.episode.title}: {exc}")
    return additional_downloads


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
        build_download_queue,
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
                    downloaded_total += _download_episodes(
                        episodes,
                        config,
                        downloaded_total=downloaded_total,
                        max_downloads=max_downloads,
                        ui=ui,
                        build_download_queue=build_download_queue,
                        download_and_upload=download_and_upload,
                        bot_detection_error=BotDetectionError,
                    )

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
