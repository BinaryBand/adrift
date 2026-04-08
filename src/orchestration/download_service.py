from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

import src.youtube.downloader as yt_downloader
from src.app_common import PodcastConfig, ensure_podcast_config, load_podcasts_config
from src.orchestration.models import (
    DownloadRunRequest,
    DownloadRunResult,
    FailedSeries,
    LogCallback,
)
from src.youtube.downloader import BotDetectionError


def _emit(message: str, callback: LogCallback | None) -> None:
    print(message)
    if callback is not None:
        callback(message)


@contextmanager
def _runtime_context(workdir: Path | None):
    original_cwd = Path.cwd()
    original_bot_detection = yt_downloader.PROPAGATE_BOT_DETECTION
    yt_downloader.PROPAGATE_BOT_DETECTION = True
    try:
        if workdir is not None:
            os.chdir(workdir)
        yield
    finally:
        os.chdir(original_cwd)
        yt_downloader.PROPAGATE_BOT_DETECTION = original_bot_detection


def run_download_pipeline(
    request: DownloadRunRequest,
    *,
    download_series: Callable[..., int],
    update_series: Callable[[PodcastConfig], None],
) -> DownloadRunResult:
    with _runtime_context(request.workdir):
        configs: list[PodcastConfig] = load_podcasts_config(include=request.include)
        configs = [ensure_podcast_config(config) for config in configs]
        _emit(f"Processing {len(configs)} podcast(s)", request.log_callback)

        remaining = request.max_downloads
        total_downloaded = 0
        failed_series: list[FailedSeries] = []
        bot_detected = False

        for config in configs:
            if not request.skip_download:
                if remaining is not None and remaining <= 0:
                    _emit(
                        "Download budget exhausted; skipping remaining series.",
                        request.log_callback,
                    )
                    break
                try:
                    _emit(f"Downloading series: {config.name}", request.log_callback)
                    downloaded = download_series(config, budget=remaining)
                    _emit(
                        f"Successfully downloaded series: {config.name} ({downloaded} new)",
                        request.log_callback,
                    )
                    total_downloaded += downloaded
                    if remaining is not None:
                        remaining -= downloaded
                except BotDetectionError as exc:
                    bot_detected = True
                    failed_series.append(FailedSeries(config.name, "download", str(exc)))
                    _emit(
                        f"ERROR: Failed to download series {config.name}: {exc}",
                        request.log_callback,
                    )
                except Exception as exc:
                    failed_series.append(FailedSeries(config.name, "download", str(exc)))
                    _emit(
                        f"ERROR: Failed to download series {config.name}: {exc}",
                        request.log_callback,
                    )

            if not request.skip_update:
                try:
                    _emit(f"Updating series: {config.name}", request.log_callback)
                    update_series(config)
                    _emit(f"Successfully updated series: {config.name}", request.log_callback)
                except Exception as exc:
                    failed_series.append(FailedSeries(config.name, "update", str(exc)))
                    _emit(
                        f"ERROR: Failed to update series {config.name}: {exc}",
                        request.log_callback,
                    )

    return DownloadRunResult(
        total_series=len(configs),
        total_episodes_downloaded=total_downloaded,
        failed_series=failed_series,
        bot_detected=bot_detected,
    )
