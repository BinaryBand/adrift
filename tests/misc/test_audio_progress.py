from src.files.audio import _maybe_report_ffmpeg_progress
from src.youtube.downloader import _extract_progress_update


def test_maybe_report_ffmpeg_progress_reports_out_time_us() -> None:
    updates: list[tuple[int, int | None]] = []

    _maybe_report_ffmpeg_progress(
        "out_time_us=2500000\n",
        5,
        lambda current, total: updates.append((current, total)),
    )

    assert updates == [(2, 5)]


def test_maybe_report_ffmpeg_progress_ignores_unrelated_lines() -> None:
    updates: list[tuple[int, int | None]] = []

    _maybe_report_ffmpeg_progress(
        "progress=continue\n",
        5,
        lambda current, total: updates.append((current, total)),
    )

    assert updates == []


def test_extract_progress_update_reports_download_bytes() -> None:
    assert _extract_progress_update(
        {
            "status": "downloading",
            "downloaded_bytes": 25,
            "total_bytes_estimate": 100,
        }
    ) == (25, 100)


def test_extract_progress_update_reports_fragment_progress_without_bytes() -> None:
    assert _extract_progress_update(
        {
            "status": "downloading",
            "fragment_index": 2,
            "fragment_count": 5,
        }
    ) == (2, 5)


def test_extract_progress_update_marks_finished_as_complete() -> None:
    assert _extract_progress_update(
        {
            "status": "finished",
            "downloaded_bytes": 100,
        }
    ) == (100, 100)
