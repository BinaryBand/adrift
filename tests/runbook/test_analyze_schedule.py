import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_load_download_targets_from_toml(tmp_path: Path) -> None:
    content = (
        '[[podcasts]]\nname = "Test Podcast"\n[[podcasts.downloads]]\nurl = "yt://@testhandle"\n'
    )
    cfg = tmp_path / "youtube.toml"
    cfg = Path(cfg)
    cfg.write_text(content)
    analyze_path = Path(__file__).parents[2] / "runbook" / "analysis" / "analyze_schedule.py"
    mod = _load_module(analyze_path, "analyze_schedule")
    setattr(mod, "CONFIG_PATH", cfg)
    targets = mod._load_download_targets()  # type: ignore
    assert isinstance(targets, list)
    assert len(targets) >= 1  # type: ignore
    assert any(getattr(t, "source", None) for t in targets)  # type: ignore


def test_parse_entry_datetime_uses_published_parsed_only() -> None:
    analyze_path = Path(__file__).parents[2] / "runbook" / "analysis" / "analyze_schedule.py"
    mod = _load_module(analyze_path, "analyze_schedule_datetime")
    entry = mod.feedparser.FeedParserDict(
        {
            "published_parsed": (2024, 1, 2, 3, 4, 5, 0, 0, 0),
            "updated_parsed": (2025, 2, 3, 4, 5, 6, 0, 0, 0),
            "published": "2024-01-02T03:04:05Z",
        }
    )

    parsed = mod._parse_entry_datetime(entry)

    assert parsed == datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def test_entry_video_id_uses_normalized_id_only() -> None:
    analyze_path = Path(__file__).parents[2] / "runbook" / "analysis" / "analyze_schedule.py"
    mod = _load_module(analyze_path, "analyze_schedule_ids")
    entry = mod.feedparser.FeedParserDict(
        {
            "id": "yt:video:abc123",
            "yt_videoid": "ignored-direct-field",
        }
    )

    video_id = mod._entry_video_id(entry)

    assert video_id == "abc123"


def test_resolve_channel_id_requires_channel_id_field() -> None:
    analyze_path = Path(__file__).parents[2] / "runbook" / "analysis" / "analyze_schedule.py"
    mod = _load_module(analyze_path, "analyze_schedule_channel_id")

    class _FakeYoutubeDl:
        def __init__(self, _opts: object) -> None:
            pass

        def __enter__(self) -> "_FakeYoutubeDl":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            assert exc_type is None, "Expected a ValueError to be raised"
            assert exc is None, "Expected a ValueError to be raised"
            assert tb is None, "Expected a ValueError to be raised"
            return False

        def extract_info(self, _url: str, download: bool = False) -> dict[str, str]:
            del download
            return {"id": "UCfallbackOnly"}

    mod.YoutubeDL = _FakeYoutubeDl  # type: ignore

    with pytest.raises(ValueError):
        mod._resolve_channel_id("https://www.youtube.com/@example/videos")
