# Thin re-export shim for S3 metadata helpers

from src.files.s3 import (
    _fetch_head_metadata,
    _public_s3_url,
    _sync_copy_cache,
    get_metadata,
    set_metadata,
)

# Keep names consistent with original module
__all__ = [
    "_sync_copy_cache",
    "_fetch_head_metadata",
    "_public_s3_url",
    "get_metadata",
    "set_metadata",
]
