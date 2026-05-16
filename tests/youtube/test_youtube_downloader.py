from pathlib import Path

import pytest
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from adrift.youtube import downloader


def test_download_video_skips_members_only_download_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise_members_only(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise YtDlpDownloadError(
            "ERROR: [youtube] 2-eSmGYUz30: Join this channel to get access to members-only content"
        )

    monkeypatch.setattr(downloader, "_run_download_attempt", _raise_members_only)
    result = downloader.download_video(
        "https://www.youtube.com/watch?v=2-eSmGYUz30",
        tmp_path,
    )

    assert result is None
