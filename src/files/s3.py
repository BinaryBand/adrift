# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
import mimetypes
import os
import sys
import time
from dataclasses import dataclass
from functools import cache, wraps
from pathlib import Path
from threading import Lock
from typing import Any, Callable, ParamSpec, TypeVar, cast
from urllib.parse import urljoin

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.client import Config
from diskcache import Cache
from dotenv import find_dotenv, load_dotenv
from mypy_boto3_s3 import S3Client
from mypy_boto3_s3.type_defs import CopySourceTypeDef
from pydantic import BaseModel, ConfigDict

sys.path.insert(0, Path(__file__).parent.parent.as_posix())
from src.models import CacheMetadata, MediaMetadata, S3Metadata
from src.utils.progress import Callback

load_dotenv(find_dotenv())
assert (S3_USERNAME := os.getenv("S3_USERNAME", "")) != "", "`S3_USERNAME` empty"
assert (S3_SECRET_KEY := os.getenv("S3_SECRET_KEY", "")) != "", "`S3_SECRET_KEY` empty"
assert (S3_ENDPOINT := os.getenv("S3_ENDPOINT", "")) != "", "`S3_ENDPOINT` empty"
assert (S3_REGION := os.getenv("S3_REGION", "")) != "", "`S3_REGION` empty"

_LOCAL_S3_ENDPOINT = os.getenv("LOCAL_S3_ENDPOINT", "http://localhost:9000")

_s3_client_lock = Lock()
_s3_client: S3Client | None = None
_effective_endpoint: str | None = None


@cache
def _s3_cache() -> Cache:
    """Get the RSS feed cache instance."""
    return Cache(".cache/s3")


_P = ParamSpec("_P")
_T = TypeVar("_T")


def retry(
    attempts: int = 3, backoff_base: int = 2
) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    """Decorator to retry a function with exponential backoff on failure."""

    def decorator(func: Callable[_P, _T]) -> Callable[_P, _T]:
        return _make_retry_wrapper(func, attempts, backoff_base)

    return decorator


def _make_retry_wrapper(
    func: Callable[_P, _T], attempts: int, backoff_base: int
) -> Callable[_P, _T]:
    @wraps(func)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        label = func.__name__
        last_exception = None
        for i in range(1, attempts + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if i < attempts:
                    wait = backoff_base**i
                    print(f"{label} attempt {i}/{attempts} failed. Wait {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"{label} failed all {attempts} attempts")

        raise last_exception  # type: ignore[misc]

    return wrapper


def _build_upload_extra_args(
    file_path: str, metadata_dict: dict[str, str] | None
) -> dict[str, Any]:
    """Build the ExtraArgs dict for a boto3 upload_file call."""
    extra_args: dict[str, Any] = {"ACL": "public-read"}
    if metadata_dict is not None:
        extra_args["Metadata"] = metadata_dict
    content_type, _ = mimetypes.guess_type(file_path)
    extra_args["ContentType"] = content_type or "application/octet-stream"
    return extra_args


def _make_upload_callback(callback: Callback, file_size: int) -> "Callable[[int], None]":
    """Wrap a progress Callback in a thread-safe boto3-compatible callable."""
    lock = Lock()
    bytes_transferred = [0]

    def _cb(bytes_chunk: int) -> None:
        with lock:
            bytes_transferred[0] += bytes_chunk
            callback(bytes_transferred[0], file_size)

    return _cb


def _make_boto_config(
    connect_timeout: float = 15, read_timeout: float = 120, max_attempts: int = 5
) -> Config:
    """Return a standardized botocore Config for S3 clients used in this module."""
    return Config(
        signature_version="s3v4",
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        retries={"max_attempts": max_attempts},
    )


def _is_endpoint_reachable(url: str, timeout: float = 2.0) -> bool:
    """Return True if an actual S3 API call succeeds against the endpoint.

    A plain HTTP GET (or TCP probe) is not sufficient — a reverse proxy may
    return 200 for GET / while the underlying S3 backend is still unreachable,
    causing every real S3 operation to get a 502 Bad Gateway.  We probe with
    list_buckets() so the check exercises the same code-path as normal usage.
    """
    try:
        cfg = _make_boto_config(connect_timeout=timeout, read_timeout=timeout, max_attempts=1)
        boto3_factory: Callable[..., Any] = boto3.client  # pyright: ignore[reportUnknownVariableType]
        client = cast(  # pyright: ignore[reportUnknownVariableType]
            S3Client,
            boto3_factory(
                "s3",
                aws_access_key_id=S3_USERNAME,
                aws_secret_access_key=S3_SECRET_KEY,
                endpoint_url=url,
                config=cfg,
                region_name=S3_REGION,
            ),
        )
        client.list_buckets()
        return True
    except Exception:
        return False


@dataclass
class _UploadSpec:
    bucket: str
    key: str
    file_path: str
    extra_args: dict[str, Any]
    boto_callback: Callable[[int], None] | None = None


def _do_s3_upload(spec: _UploadSpec) -> None:
    """Execute the actual S3 multipart upload via boto3."""
    transfer_config = TransferConfig(
        max_concurrency=4,
        multipart_threshold=8 * 1024 * 1024,
        multipart_chunksize=8 * 1024 * 1024,
        use_threads=True,
    )
    get_s3_client().upload_file(
        Filename=spec.file_path,
        Bucket=spec.bucket,
        Key=spec.key,
        ExtraArgs=spec.extra_args,
        Config=transfer_config,
        Callback=spec.boto_callback,
    )


def _sync_upload_cache(bucket: str, key: str, metadata_dict: dict[str, str] | None) -> None:
    """Update the local S3 metadata cache after an upload."""
    cache_key = f"s3_metadata:{bucket}:{key}"
    if metadata_dict is not None:
        _s3_cache().set(cache_key, metadata_dict)
    else:
        _s3_cache().delete(cache_key)


def _get_effective_s3_endpoint() -> str:
    """Resolve the endpoint boto3 should talk to."""
    global _effective_endpoint

    if _effective_endpoint is not None:
        return _effective_endpoint

    # Prefer local endpoint if it's reachable.
    if _LOCAL_S3_ENDPOINT and _is_endpoint_reachable(_LOCAL_S3_ENDPOINT):
        _effective_endpoint = _LOCAL_S3_ENDPOINT
    else:
        _effective_endpoint = S3_ENDPOINT

    return _effective_endpoint


def get_s3_client() -> S3Client:
    """Get a cached S3 client."""
    global _s3_client

    if _s3_client is not None:
        return _s3_client

    with _s3_client_lock:
        if _s3_client is not None:
            return _s3_client

        _s3_client = _build_s3_client()
        return _s3_client


def _build_s3_client() -> S3Client:
    """Construct a new boto3 S3 client (not cached).

    Exposed as a helper so client construction can be replaced or mocked
    independently of the caching layer in `get_s3_client()`.
    """
    session = boto3.session.Session()

    cfg = _make_boto_config()
    session_factory: Callable[..., Any] = session.client  # pyright: ignore[reportUnknownVariableType]

    return cast(  # pyright: ignore[reportUnknownVariableType]
        S3Client,
        session_factory(
            "s3",
            aws_access_key_id=S3_USERNAME,
            aws_secret_access_key=S3_SECRET_KEY,
            # Use local shortcut endpoint when available; keep S3_ENDPOINT as public.
            endpoint_url=_get_effective_s3_endpoint(),
            config=cfg,
            region_name=S3_REGION,
        ),
    )


@retry(attempts=5, backoff_base=2)
def download_file(bucket: str, key: str, download_path: Path) -> None:
    """Download file using authenticated S3 client"""
    client = get_s3_client()
    response = client.get_object(Bucket=bucket, Key=key)

    with open(download_path, "wb") as f:
        for chunk in response["Body"].iter_chunks():
            f.write(chunk)


class UploadOptions(BaseModel):
    """Options model for `upload_file`.

    Uses arbitrary types to allow passing a `Callback` callable.
    """

    metadata: S3Metadata | None = None
    callback: Callback | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


def _prepare_upload_spec(
    bucket: str,
    key: str,
    file_path: Path | str,
    options: UploadOptions | S3Metadata | dict[str, Any] | None,
) -> tuple[_UploadSpec, dict[str, str] | None]:
    """Prepare an _UploadSpec and metadata dict from common upload inputs.

    Extracted to keep `upload_file` short and focused on orchestration.
    """
    _file_path = file_path if isinstance(file_path, str) else file_path.as_posix()
    assert os.path.exists(_file_path), f"Local file not found: {file_path}"

    metadata, callback = _extract_upload_options(options)
    metadata_dict = metadata.to_dict() if metadata is not None else None
    boto_callback = _build_boto_callback_for_file(_file_path, callback)

    spec = _UploadSpec(
        bucket=bucket,
        key=key,
        file_path=_file_path,
        extra_args=_build_upload_extra_args(_file_path, metadata_dict),
        boto_callback=boto_callback,
    )
    return spec, metadata_dict


def _extract_upload_options(
    options: UploadOptions | S3Metadata | dict[str, Any] | None,
) -> tuple[S3Metadata | None, Callback | None]:
    """Normalize `options` to (metadata, callback).

    Accepts an `UploadOptions` model, a plain `dict`, or a `MediaMetadata`
    instance for backward compatibility.
    """
    if options is None:
        return None, None
    if isinstance(options, S3Metadata):
        return options, None
    if isinstance(options, UploadOptions):
        return options.metadata, options.callback
    # Fall back: attempt to treat remaining values as a dict-like options
    # mapping. This avoids an `isinstance(..., dict)` check which can be
    # noisy for the static checker in some union scenarios.
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
    """Return a boto3-compatible callback for `file_path` or None."""
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
            # Prefer calling with (value, total_value) when supported
            callback_raw(value, total_value)
        except TypeError:
            try:
                # Fallback to single-arg callbacks (boto style)
                callback_raw(value)
            except Exception:
                # Swallow any exceptions from user callback
                return

    return _adapted


@retry(attempts=3, backoff_base=2)
def upload_file(
    bucket: str,
    key: str,
    file_path: Path,
    options: UploadOptions | MediaMetadata | dict[str, Any] | None = None,
) -> str | None:
    """Upload a file to S3.

    The `options` argument may be one of:
      - `None` (no metadata or callback)
      - a `MediaMetadata` instance (metadata only)
      - an `UploadOptions` dict with optional keys `metadata` and `callback`
    """
    spec, metadata_dict = _prepare_upload_spec(bucket, key, file_path, options)
    _do_s3_upload(spec)
    _sync_upload_cache(bucket, key, metadata_dict)
    return urljoin(S3_ENDPOINT, Path(bucket, key).as_posix())


@retry(attempts=3, backoff_base=2)
def upload_cache_file(
    bucket: str,
    key: str,
    file_path: Path,
    metadata: CacheMetadata | None = None,
) -> str | None:
    spec, metadata_dict = _prepare_upload_spec(bucket, key, file_path, metadata)
    _do_s3_upload(spec)
    _sync_upload_cache(bucket, key, metadata_dict)
    return urljoin(S3_ENDPOINT, Path(bucket, key).as_posix())


@retry(attempts=3, backoff_base=2)
def delete_file(bucket: str, key: str) -> None:
    client: S3Client = get_s3_client()
    client.delete_object(Bucket=bucket, Key=key)

    cache_key = f"s3_metadata:{bucket}:{key}"
    _s3_cache().delete(cache_key)


def rename_file(bucket: str, old_key: str, new_key: str) -> None:
    if old_key == new_key:
        return

    client: S3Client = get_s3_client()

    copy_source: CopySourceTypeDef = {"Bucket": bucket, "Key": old_key}
    client.copy_object(Bucket=bucket, Key=new_key, CopySource=copy_source, MetadataDirective="COPY")
    client.delete_object(Bucket=bucket, Key=old_key)

    old_cache_key = f"s3_metadata:{bucket}:{old_key}"
    new_cache_key = f"s3_metadata:{bucket}:{new_key}"
    _s3_cache().set(new_cache_key, _s3_cache().get(old_cache_key))
    _s3_cache().delete(old_cache_key)


def get_metadata(bucket: str, key: str) -> MediaMetadata | None:
    key = Path(key).as_posix()
    cache_key = f"s3_metadata:{bucket}:{key}"
    metadata = _s3_cache().get(cache_key)

    if metadata is None and exists(bucket, key) is not None:
        client: S3Client = get_s3_client()
        head_response = client.head_object(Bucket=bucket, Key=key)
        metadata = head_response.get("Metadata", {})
        _s3_cache().set(cache_key, metadata)

    try:
        return MediaMetadata.model_validate(metadata)
    except Exception:
        return None


def set_metadata(bucket: str, key: str, metadata: MediaMetadata) -> None:
    key = Path(key).as_posix()
    metadata_dict = metadata.to_dict()

    client: S3Client = get_s3_client()
    client.copy_object(
        Bucket=bucket,
        Key=key,
        CopySource={"Bucket": bucket, "Key": key},
        Metadata=metadata_dict,
        MetadataDirective="REPLACE",
        ACL="public-read",
    )

    cache_key = f"s3_metadata:{bucket}:{key}"
    _s3_cache().set(cache_key, metadata_dict)


def _build_file_map_from_iterator(
    bucket: str, prefix: str, without_extensions: bool
) -> dict[str, str]:
    """Build a file->etag map from the iterator that yields S3 objects.

    Extracted so pagination and mapping logic can be tested or swapped
    independently of the cache handling in `_get_file_map()`.
    """
    file_list: dict[str, str] = {}
    for obj in _iterate_s3_objects(bucket, prefix):
        key = obj.get("Key", "")
        file_name = Path(key).name

        if without_extensions:
            file_name = Path(file_name).with_suffix("").as_posix()

        etag = obj.get("ETag", "").strip('"')[:32]
        file_list[file_name] = etag

    return file_list


def _get_file_map(bucket: str, prefix: str, without_extensions: bool = True) -> dict[str, str]:
    # Normalize prefix - add trailing slash for directory listing with delimiter
    prefix = prefix.lstrip(".")
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    cache_key = f"s3_file_map:{bucket}:{prefix}:{without_extensions}"
    cached_map = _s3_cache().get(cache_key)
    if cached_map is not None:
        return cached_map

    file_list = _build_file_map_from_iterator(bucket, prefix, without_extensions)
    _s3_cache().set(cache_key, file_list, expire=10)
    return file_list


def _iterate_s3_objects(bucket: str, prefix: str):
    """Yield object dicts for all objects under `bucket/prefix`.

    Extracted from `_get_file_map()` so pagination can be tested or swapped
    independently of the mapping/ETag logic.
    """
    s3: S3Client = get_s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/")

    for page in page_iterator:
        for obj in page.get("Contents", {}):
            yield obj


def _remove_file_extensions(file_names: list[str]) -> list[str]:
    return [Path(f).with_suffix("").as_posix() for f in file_names]


def get_file_list(bucket: str, prefix: str, without_extensions: bool = False) -> list[str]:
    prefix = prefix.lstrip(".").rstrip("/")
    file_map = _get_file_map(bucket, prefix, False)

    file_list = list(file_map.keys())
    if without_extensions:
        file_list = _remove_file_extensions(file_list)

    return file_list


def exists(bucket: str, prefix: str, extension_agnostic: bool = True) -> str | None:
    prefix = prefix.lstrip(".").rstrip("/")
    key: Path = Path(prefix)

    # Get parent directory to list files from, not the full path
    parent_dir = key.parent.as_posix()
    if parent_dir == ".":
        parent_dir = ""

    identifier = key.stem if extension_agnostic else key.name
    file_list: list[str] = get_file_list(bucket, parent_dir, False)

    for f in file_list:
        if _identifier_matches(f, identifier, extension_agnostic):
            return f

    return None


def _identifier_matches(name: str, identifier: str, extension_agnostic: bool) -> bool:
    """Return True if `name` matches `identifier` under the extension policy."""
    if extension_agnostic:
        return Path(name).with_suffix("").as_posix() == identifier
    return name == identifier
