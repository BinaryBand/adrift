"""S3 path helpers used by the download modules."""

from pathlib import Path

from src.models import PodcastConfig


def _s3_prefix(config: PodcastConfig) -> tuple[str, str]:
    """Parse config.path '/media/podcasts/slug' → ('media', 'podcasts/slug')."""
    parts = Path(config.path).parts
    return parts[1], "/".join(parts[2:])


def _prefixed_s3_key(prefix: str, name: str) -> str:
    return f"{prefix}/{name}" if prefix else name


__all__ = ["_s3_prefix", "_prefixed_s3_key"]
