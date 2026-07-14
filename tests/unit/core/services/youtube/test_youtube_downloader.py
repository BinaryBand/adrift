from pathlib import Path

import pytest
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from adrift.adapters.process.youtube import downloader


def test_download_video_skips_members_only_download_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise_members_only(*args: object, **kwargs: object) -> None:
        del args, kwargs
        msg = (
            "ERROR: [youtube] 2-eSmGYUz30: Join this channel to get access to members-only content"
        )
        raise YtDlpDownloadError(msg)

    monkeypatch.setattr(downloader, "_run_download_attempt", _raise_members_only)
    result = downloader.download_video(
        "https://www.youtube.com/watch?v=2-eSmGYUz30",
        tmp_path,
    )

    assert result is None


def test_download_video_retries_after_http_403(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    audio_path = tmp_path / "dQw4w9WgXcQ.m4a"

    def _forbidden_then_success(*args: object, **kwargs: object) -> Path:
        del args, kwargs
        calls.append(1)
        if len(calls) == 1:
            msg = "ERROR: unable to download video data: HTTP Error 403: Forbidden"
            raise YtDlpDownloadError(msg)
        return audio_path

    monkeypatch.setattr(downloader, "_run_download_attempt", _forbidden_then_success)
    result = downloader.download_video(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        tmp_path,
    )

    assert result == audio_path
    assert len(calls) == 2


def test_download_video_exhausts_attempts_on_persistent_403(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def _always_forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        calls.append(1)
        msg = "ERROR: unable to download video data: HTTP Error 403: Forbidden"
        raise YtDlpDownloadError(msg)

    monkeypatch.setattr(downloader, "_run_download_attempt", _always_forbidden)
    result = downloader.download_video(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        tmp_path,
    )

    assert result is None
    assert len(calls) == len(downloader._DOWNLOAD_ATTEMPTS)
