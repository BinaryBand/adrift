"""Adapter implementations for various ports.

Lazy imports inside factory functions are intentional: they prevent circular
imports between the adapters package and the modules it depends on.  The
registries below are the single points of extension — to add a new provider
or source type, add one entry here without touching any function body.
"""

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


# --- Episode source registry ------------------------------------------------
# Each entry is (url_predicate, adapter_factory).  The first matching predicate
# wins.  Adding a new source type = one new tuple here, nothing else changes.


def _make_youtube_source() -> EpisodeSourcePort:
    from src.adapters.episode_sources.episode_source_youtube import YouTubeEpisodeSourceAdapter

    return YouTubeEpisodeSourceAdapter()


def _make_rss_source() -> EpisodeSourcePort:
    from src.adapters.episode_sources.episode_source_rss import RssEpisodeSourceAdapter

    return RssEpisodeSourceAdapter()


_SOURCE_REGISTRY: list[tuple[Callable[[str], bool], Callable[[], EpisodeSourcePort]]] = [
    (is_youtube_channel, _make_youtube_source),
]
_DEFAULT_SOURCE_FACTORY: Callable[[], EpisodeSourcePort] = _make_rss_source


def get_episode_source_adapter(source: FeedSource) -> EpisodeSourcePort:
    """Return the appropriate episode source adapter for a FeedSource.

    Dispatch is driven by ``_SOURCE_REGISTRY``; callers should use the returned
    adapter rather than importing source-specific modules directly.
    """
    url = _require_source_url(source)
    for predicate, factory in _SOURCE_REGISTRY:
        if predicate(url):
            return factory()
    return _DEFAULT_SOURCE_FACTORY()


# --- Secret provider registry -----------------------------------------------
# Maps provider name → factory function.  Adding a new provider = one new
# entry here; get_secret_provider_adapter is never modified.


def _make_env_provider() -> SecretProviderPort:
    from src.adapters.secrets.env_secrets import EnvironmentSecretProvider

    return EnvironmentSecretProvider()


_SECRET_PROVIDER_REGISTRY: dict[str, Callable[[], SecretProviderPort]] = {
    "env": _make_env_provider,
}


def _selected_provider_name(provider_name: str | None) -> str:
    return (provider_name or os.getenv("ADRIFT_SECRETS_PROVIDER") or "env").lower()


def get_secret_provider_adapter(
    provider_name: str | None = None,
    *,
    enable_prompt_fallback: bool | None = None,
    prompt_callback: Callable[[str, str, bool], str] | None = None,
) -> SecretProviderPort:
    """Return the configured secret provider adapter instance."""
    selected = _selected_provider_name(provider_name)
    factory = _SECRET_PROVIDER_REGISTRY.get(selected)
    if factory is None:
        raise ValueError(f"Unsupported secret provider: {selected}")
    provider = factory()

    if enable_prompt_fallback is None:
        raw = os.getenv("ADRIFT_SECRETS_PROMPT_FALLBACK", "").strip().lower()
        enable_prompt_fallback = raw in {"1", "true", "yes", "on"}

    if not enable_prompt_fallback:
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
    selected = _selected_provider_name(provider_name)
    factory = _SECRET_PROVIDER_REGISTRY.get(selected)
    if factory is None:
        raise ValueError(f"Unsupported secret provider: {selected}")
    provider = factory()

    if getattr(provider, "writable", False):
        from src.adapters.secrets.env_secrets import EnvironmentSecretStore

        return EnvironmentSecretStore(env_file=env_file)

    from src.adapters.secrets.read_only_store import ReadOnlySecretStore
    from src.orchestration.secret_service import MANAGED_S3_KEYS

    return ReadOnlySecretStore(provider, known_keys=MANAGED_S3_KEYS)


# --- Other adapters ---------------------------------------------------------


def get_alignment_adapter():
    """Return the default alignment adapter instance."""
    from src.adapters.alignment import GreedyAlignmentAdapter

    return GreedyAlignmentAdapter()


def get_mermaid_adapter():
    """Return the default Mermaid adapter instance."""
    from src.adapters.mermaid import FileMermaidAdapter

    return FileMermaidAdapter()


def get_report_adapter():
    """Return the default report adapter instance."""
    return None
