from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from boto3.s3.transfer import TransferConfig

from src.files.s3_types import UploadOptions, _UploadSpec
from src.files.s3_utils import _build_upload_extra_args, _make_upload_callback
from src.models import CacheMetadata, MediaMetadata, S3Metadata
from src.utils.progress import Callback

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
else:
    S3Client = Any


def _do_s3_upload(client: S3Client, spec: _UploadSpec) -> None:
    transfer_config = TransferConfig(
        max_concurrency=4,
        multipart_threshold=8 * 1024 * 1024,
        multipart_chunksize=8 * 1024 * 1024,
        use_threads=True,
    )
    client.upload_file(
        Filename=spec.file_path,
        Bucket=spec.bucket,
        Key=spec.key,
        ExtraArgs=spec.extra_args,
        Config=transfer_config,
        Callback=spec.boto_callback,
    )


def _prepare_upload_spec(
    bucket: str,
    key: str,
    file_path: Path | str,
    options: UploadOptions | S3Metadata | dict[str, Any] | None,
) -> tuple[_UploadSpec, dict[str, str] | None]:
    resolved_file_path = file_path if isinstance(file_path, str) else file_path.as_posix()
    if not os.path.exists(resolved_file_path):
        raise FileNotFoundError(f"Local file not found: {resolved_file_path}")

    metadata, callback = _extract_upload_options(options)
    metadata_dict = metadata.to_dict() if metadata is not None else None
    boto_callback = _build_boto_callback_for_file(resolved_file_path, callback)

    spec = _UploadSpec(
        bucket=bucket,
        key=key,
        file_path=resolved_file_path,
        extra_args=_build_upload_extra_args(resolved_file_path, metadata_dict),
        boto_callback=boto_callback,
    )
    return spec, metadata_dict


def _extract_upload_options(
    options: UploadOptions | S3Metadata | dict[str, Any] | None,
) -> tuple[S3Metadata | None, Callback | None]:
    if options is None:
        return None, None
    if isinstance(options, S3Metadata):
        return options, None
    if isinstance(options, UploadOptions):
        return options.metadata, options.callback
    try:
        return _extract_upload_options_from_dict(options)
    except Exception:
        return None, None


def _extract_upload_options_from_dict(
    options: dict[str, Any],
) -> tuple[S3Metadata | None, Callback | None]:
    try:
        opts = UploadOptions.model_validate(options)
        return opts.metadata, opts.callback
    except Exception:
        metadata_obj = _validate_metadata_raw(options.get("metadata"))
        callback_obj = _adapt_callback_obj(options.get("callback"))
        return metadata_obj, callback_obj


def _build_boto_callback_for_file(
    file_path: str, callback: Callback | None
) -> Callable[[int], None] | None:
    if callback is None:
        return None
    return _make_upload_callback(callback, os.path.getsize(file_path))


def _validate_metadata_raw(metadata_raw: Any) -> S3Metadata | None:
    try:
        return MediaMetadata.model_validate(metadata_raw)
    except Exception:
        try:
            return CacheMetadata.model_validate(metadata_raw)
        except Exception:
            if isinstance(metadata_raw, (MediaMetadata, CacheMetadata)):
                return metadata_raw
            return None


def _adapt_callback_obj(callback_raw: Any) -> Callback | None:
    if not callable(callback_raw):
        return None

    def _adapted(value: int, total_value: int | None) -> None:
        try:
            callback_raw(value, total_value)
        except TypeError:
            try:
                callback_raw(value)
            except Exception:
                return

    return _adapted


__all__ = [
    "_do_s3_upload",
    "_prepare_upload_spec",
    "_extract_upload_options",
    "_extract_upload_options_from_dict",
    "_build_boto_callback_for_file",
    "_validate_metadata_raw",
    "_adapt_callback_obj",
    "UploadOptions",
]
