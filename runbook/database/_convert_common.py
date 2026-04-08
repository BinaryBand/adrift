import glob
from pathlib import Path

from src.app_common import load_config

CONFIG_GLOB = "config/*.toml"


def format_bytes(size: int) -> str:
    """Format bytes into a human-readable string."""
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def collect_podcast_targets(config_glob: str = CONFIG_GLOB) -> list[tuple[str, str]]:
    """Load all podcast targets from config files as (bucket, prefix)."""
    targets: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for config_path in sorted(glob.glob(config_glob)):
        try:
            configs = load_config(config_path)
        except Exception as e:
            print(f"WARNING: Failed loading {config_path}: {e}")
            continue

        for config in configs:
            raw = Path(config.path)
            if len(raw.parts) < 3:
                print(f"WARNING: Invalid podcast path format in {config_path}: {config.path}")
                continue
            target = (raw.parts[1], Path(*raw.parts[2:]).as_posix())
            if target in seen:
                continue
            seen.add(target)
            targets.append(target)

    return targets
