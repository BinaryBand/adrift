"""Compatibility shim for legacy download cache imports."""

from src.application.services.download_cache import _existing_media_sources, _ExistingMediaSources

__all__ = ["_existing_media_sources", "_ExistingMediaSources"]
