"""Adapter implementations for various ports."""

import os

from src.app_common import FeedSource
from src.ports.episode_source import EpisodeSourcePort
from src.utils.text import is_youtube_channel


def get_episode_source_adapter(source: FeedSource) -> EpisodeSourcePort:
    """Get the appropriate episode source adapter for a FeedSource.

    Routes to YouTube adapter if URL is a YouTube channel, otherwise RSS adapter.

    Args:
        source: FeedSource with URL to analyze

    Returns:
        EpisodeSourcePort adapter instance
    """
    url = source.url
    if not url:
        raise ValueError("FeedSource URL is required to determine adapter")

    if is_youtube_channel(url):
        from src.adapters.episode_sources.episode_source_youtube import YouTubeEpisodeSourceAdapter

        return YouTubeEpisodeSourceAdapter()
    else:
        from src.adapters.episode_sources.episode_source_rss import RssEpisodeSourceAdapter

        return RssEpisodeSourceAdapter()


def get_alignment_adapter():
    """Return the default alignment adapter instance.

    This is a thin factory so callers can obtain a pluggable alignment
    implementation without importing adapter modules at module import time.
    """
    from src.adapters.alignment import GreedyAlignmentAdapter

    return GreedyAlignmentAdapter()


def get_mermaid_adapter():
    """Return the default Mermaid adapter instance."""
    from src.adapters.mermaid import FileMermaidAdapter

    return FileMermaidAdapter()


def get_report_adapter():
    """Return the default report adapter instance."""
    from src.adapters.report import FileReportAdapter

    return FileReportAdapter()


def get_secret_provider_adapter(provider_name: str | None = None):
    """Return the configured secret provider adapter instance."""
    selected = (provider_name or os.getenv("ADRIFT_SECRETS_PROVIDER", "env")).lower()
    if selected == "docker":
        from src.adapters.secrets.docker_secrets import DockerSecretProvider

        return DockerSecretProvider()

    if selected == "env":
        from src.adapters.secrets.env_secrets import EnvironmentSecretProvider

        return EnvironmentSecretProvider()

    raise ValueError(f"Unsupported secret provider: {selected}")


def get_secret_store_adapter(provider_name: str | None = None, *, env_file: str = ".env"):
    """Return a writable secret store for the selected provider."""
    selected = (provider_name or os.getenv("ADRIFT_SECRETS_PROVIDER", "env")).lower()
    if selected == "env":
        from src.adapters.secrets.env_secrets import EnvironmentSecretStore

        return EnvironmentSecretStore(env_file=env_file)

    raise ValueError(f"Secret store is not writable for provider: {selected}")
