"""Compatibility shim for legacy download enrichment imports."""

from src.application.services.download_enrich import _extract_video_id, enrich_with_sponsors

__all__ = ["enrich_with_sponsors", "_extract_video_id"]
