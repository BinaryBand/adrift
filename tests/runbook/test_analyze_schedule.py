import importlib.util
import sys
from pathlib import Path


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "analyze_schedule",
        Path(__file__).parents[2] / "runbook" / "analysis" / "analyze_schedule.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["analyze_schedule"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_load_download_targets_from_toml(tmp_path):
    content = (
        '[[podcasts]]\nname = "Test Podcast"\n[[podcasts.downloads]]\nurl = "yt://@testhandle"\n'
    )
    cfg = tmp_path / "youtube.toml"
    cfg.write_text(content)
    mod = _load_module()
    mod.CONFIG_PATH = cfg
    targets = mod._load_download_targets()
    assert isinstance(targets, list)
    assert len(targets) >= 1
    assert any(getattr(t, "source", None) for t in targets)
