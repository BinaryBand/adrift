import importlib.util
import sys
from pathlib import Path


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
