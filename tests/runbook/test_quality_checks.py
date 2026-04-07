import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_validate_configs():
    mod = _load_module(
        Path(__file__).parents[2] / "runbook" / "quality" / "validate_configs.py",
        "validate_configs",
    )
    cfg_dir = Path(__file__).parents[2] / "config"
    files = [p for p in cfg_dir.glob("*.toml")]
    rc = mod._scan_files(files, problems=False)
    assert rc == 0, "TOML config validation failed"


def test_static_checks():
    mod = _load_module(
        Path(__file__).parents[2] / "runbook" / "quality" / "check_static.py",
        "check_static",
    )
    paths = getattr(mod, "_DEFAULT_PATHS", ["src", "runbook", "tests", "typings"])
    overall_rc, diags = mod.run_checks(paths, None, None)
    if overall_rc == 2:
        pytest.skip("pyright or ruff not available")
    assert overall_rc == 0, f"Static checks failed: {len(diags)} diagnostics"


def test_dead_code_checks():
    mod = _load_module(
        Path(__file__).parents[2] / "runbook" / "quality" / "check_dead_code.py",
        "check_dead_code",
    )
    # Detect vulture without importing it (avoids linting unused-import warnings)
    if importlib.util.find_spec("vulture") is None:
        pytest.skip("vulture not installed")
    output = mod.run_vulture(["src"], min_confidence=80)
    diags = mod.parse_vulture_output(output)
    errors = [d for d in diags if d.severity == "error"]
    assert not errors, f"Vulture reported {len(errors)} errors"


def test_complexity_checks():
    mod = _load_module(
        Path(__file__).parents[2] / "runbook" / "quality" / "check_complexity.py",
        "check_complexity",
    )
    # Detect lizard without importing it (avoids linting unused-import warnings)
    if importlib.util.find_spec("lizard") is None:
        pytest.skip("lizard not installed")
    output = mod.run_lizard("src", ccn=5, length=25, params=4, exclude=None)
    ceiling = mod.Ceiling(ccn=5, length=25, params=4)
    rc = mod.check_metrics(output, ceiling, warn_at_ceiling=False)
    assert rc == 0, f"Complexity checks reported {rc} diagnostics"
