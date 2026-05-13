"""Compatibility shim for legacy download client imports."""

from src.application.services.download_client import prefixed_s3_key, s3_prefix

__all__ = ["s3_prefix", "prefixed_s3_key"]
