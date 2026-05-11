"""Adapter implementations for various ports."""

import os
from collections.abc import Callable

from src.models import FeedSource
from src.ports import (
    EpisodeSourcePort,
    ReadOnlySecretStorePort,
    SecretProviderPort,
    SecretStorePort,
)
from src.utils.text import is_youtube_channel


def _require_source_url(source: FeedSource) -> str:
    url = source.url
    if not url:
        raise ValueError("FeedSource URL is required")
    return url


def get_episode_source_adapter(source: FeedSource) -> EpisodeSourcePort:
    """Return the appropriate episode source adapter for a FeedSource.

    Routes to the YouTube adapter when the URL is a YouTube channel, otherwise
    to the RSS adapter.  This is the single dispatch point for source type —
    callers should use the returned adapter's methods rather than calling
    source-specific functions directly.
    """
    url = _require_source_url(source)
    if is_youtube_channel(url):
        from src.adapters.episode_sources.episode_source_youtube import YouTubeEpisodeSourceAdapter

        return YouTubeEpisodeSourceAdapter()

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
    return None


def _resolve_secret_provider_name(provider_name: str | None = None) -> str:
    raw = provider_name or os.getenv("ADRIFT_SECRETS_PROVIDER") or "env"
    return raw.lower()


def _is_prompt_fallback_enabled(enable_prompt_fallback: bool | None) -> bool:
    if enable_prompt_fallback is not None:
        return enable_prompt_fallback
    raw_value = os.getenv("ADRIFT_SECRETS_PROMPT_FALLBACK", "").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def _get_base_secret_provider(selected: str):
    if selected == "env":
        from src.adapters.secrets.env_secrets import EnvironmentSecretProvider

        return EnvironmentSecretProvider()

    raise ValueError(f"Unsupported secret provider: {selected}")


def get_secret_provider_adapter(
    provider_name: str | None = None,
    *,
    enable_prompt_fallback: bool | None = None,
    prompt_callback: Callable[[str, str, bool], str] | None = None,
) -> SecretProviderPort:
    """Return the configured secret provider adapter instance."""
    selected = _resolve_secret_provider_name(provider_name)
    provider = _get_base_secret_provider(selected)
    if not _is_prompt_fallback_enabled(enable_prompt_fallback):
        return provider

    from src.adapters.secrets.prompt_fallback import PromptFallbackProvider

    if prompt_callback is None:
        return PromptFallbackProvider(provider)
    return PromptFallbackProvider(provider, prompt_callback=prompt_callback)


def get_secret_store_adapter(
    provider_name: str | None = None,
    *,
    env_file: str = ".env",
) -> ReadOnlySecretStorePort | SecretStorePort:
    """Return a store-like adapter for the selected provider.

    Providers that expose ``writable = True`` (currently only 'env') get a
    full ``SecretStorePort``; all others are wrapped in a read-only view.
    """
    selected = _resolve_secret_provider_name(provider_name)
    provider = _get_base_secret_provider(selected)

    if getattr(provider, "writable", False):
        from src.adapters.secrets.env_secrets import EnvironmentSecretStore

        return EnvironmentSecretStore(env_file=env_file)

    from src.adapters.secrets.read_only_store import ReadOnlySecretStore
    from src.orchestration.secret_service import MANAGED_S3_KEYS

    return ReadOnlySecretStore(provider, known_keys=MANAGED_S3_KEYS)
