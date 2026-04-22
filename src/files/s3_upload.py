# Thin re-export shim for S3 upload helpers and wrappers

from src.files.s3 import (
    UploadOptions,
    _adapt_callback_obj,
    _build_boto_callback_for_file,
    _do_s3_upload,
    _extract_upload_options,
    _extract_upload_options_from_dict,
    _prepare_upload_spec,
    _validate_metadata_raw,
    upload_cache_file,
    upload_file,
)

__all__ = [
    "_do_s3_upload",
    "_prepare_upload_spec",
    "_extract_upload_options",
    "_extract_upload_options_from_dict",
    "_build_boto_callback_for_file",
    "_validate_metadata_raw",
    "_adapt_callback_obj",
    "upload_file",
    "upload_cache_file",
    "UploadOptions",
]
