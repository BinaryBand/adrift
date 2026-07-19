"""Storage path helpers used by application download services."""

from pathlib import Path

from adrift.models import PodcastConfig


def storage_prefix(config: PodcastConfig) -> tuple[str, str]:
    """Parse config.path '/media/podcasts/slug' -> ('media', 'podcasts/slug')."""
    parts = Path(config.path).parts
    return parts[1], "/".join(parts[2:])


def prefixed_key(prefix: str, name: str) -> str:
    return f"{prefix}/{name}" if prefix else name


__all__ = ["storage_prefix", "prefixed_key"]
