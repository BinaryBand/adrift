"""Adapter implementations for various ports.

Lazy imports inside factory functions are intentional: they prevent circular
imports between the adapters package and the modules it depends on.  The
registries below are the single points of extension — to add a new provider
or source type, add one entry here without touching any function body.
"""

import os
from collections.abc import Callable

from adrift.models import FeedSource
from adrift.models.ports import (
    EpisodeSourcePort,
    ScoredAlignmentBatchPort,
    ScoredAlignmentPort,
    SecretProviderPort,
)
from adrift.utils.text import is_youtube_channel


def _require_source_url(source: FeedSource) -> str:
    url = source.url
    if not url:
        raise ValueError("FeedSource URL is required")
    return url


# --- Episode source registry ------------------------------------------------
# Each entry is (url_predicate, adapter_factory).  The first matching predicate
# wins.  Adding a new source type = one new tuple here, nothing else changes.


def _make_youtube_source() -> EpisodeSourcePort:
    from adrift.adapters.process.episode_sources.episode_source_youtube import (
        YouTubeEpisodeSourceAdapter,
    )

    return YouTubeEpisodeSourceAdapter()


def _make_rss_source() -> EpisodeSourcePort:
    from adrift.adapters.process.episode_sources.episode_source_rss import (
        RssEpisodeSourceAdapter,
    )

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
    from adrift.adapters.process.secrets.env_secrets import EnvironmentSecretProvider

    return EnvironmentSecretProvider()


_SECRET_PROVIDER_REGISTRY: dict[str, Callable[[], SecretProviderPort]] = {
    "env": _make_env_provider,
}


def _selected_provider_name(provider_name: str | None) -> str:
    return (provider_name or os.getenv("ADRIFT_SECRETS_PROVIDER") or "env").lower()


def _build_selected_provider(provider_name: str | None) -> tuple[str, SecretProviderPort]:
    selected = _selected_provider_name(provider_name)
    factory = _SECRET_PROVIDER_REGISTRY.get(selected)
    if factory is None:
        raise ValueError(f"Unsupported secret provider: {selected}")
    return selected, factory()


def get_secret_provider_adapter(
    provider_name: str | None = None,
) -> SecretProviderPort:
    """Return the configured secret provider adapter instance."""
    _selected, provider = _build_selected_provider(provider_name)
    return provider


def _make_optimized_scored_alignment_adapter() -> ScoredAlignmentPort:
    from adrift.adapters.process.alignment import OptimizedScoredAlignmentAdapter

    return OptimizedScoredAlignmentAdapter()


def _make_rust_scored_alignment_adapter() -> ScoredAlignmentBatchPort:
    from adrift.adapters.process.alignment import RustScoredAlignmentAdapter

    return RustScoredAlignmentAdapter()


_SCORED_ALIGNMENT_REGISTRY: dict[
    str,
    Callable[[], ScoredAlignmentPort | ScoredAlignmentBatchPort | None],
] = {
    "optimized": _make_optimized_scored_alignment_adapter,
    "rust": _make_rust_scored_alignment_adapter,
    "legacy": lambda: None,
}


def get_scored_alignment_adapter(
    backend_name: str | None = None,
) -> ScoredAlignmentPort | ScoredAlignmentBatchPort | None:
    """Return a scored alignment adapter backend, or None for legacy service implementation.

    Priority:
    1. If backend_name is explicitly passed, use it.
    2. If ADRIFT_ALIGNMENT_BACKEND env var is set, use it.
    3. Otherwise, try to load Rust backend (with auto-compile if needed).
    4. Fall back to legacy if Rust is not available.
    """
    from adrift.adapters.process.alignment import should_use_rust_backend

    explicit_backend = backend_name or os.getenv("ADRIFT_ALIGNMENT_BACKEND", "").lower()

    if explicit_backend:
        selected = explicit_backend
    elif should_use_rust_backend():
        selected = "rust"
    else:
        selected = "legacy"

    factory = _SCORED_ALIGNMENT_REGISTRY.get(selected)
    if factory is None:
        raise ValueError(f"Unsupported alignment backend: {selected}")
    return factory()
