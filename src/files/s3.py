from mypy_boto3_s3.type_defs import CopySourceTypeDef
from boto3.s3.transfer import TransferConfig
from botocore.client import Config
from mypy_boto3_s3 import S3Client

from dotenv import load_dotenv, find_dotenv
from urllib.parse import urljoin
from functools import cache, wraps
from dataclasses import dataclass
from diskcache import Cache
from threading import Lock
from pathlib import Path
from typing import cast, Callable

import mimetypes
import boto3
import time
import sys
import os

sys.path.insert(0, Path(__file__).parent.parent.as_posix())
from src.models import MediaMetadata, CacheMetadata
from src.utils.progress import Callback


load_dotenv(find_dotenv())
assert (S3_USERNAME := os.getenv("S3_USERNAME", "")) != "", "`S3_USERNAME` empty"
assert (S3_SECRET_KEY := os.getenv("S3_SECRET_KEY", "")) != "", "`S3_SECRET_KEY` empty"
assert (S3_ENDPOINT := os.getenv("S3_ENDPOINT", "")) != "", "`S3_ENDPOINT` empty"
assert (S3_REGION := os.getenv("S3_REGION", "")) != "", "`S3_REGION` empty"

_LOCAL_S3_ENDPOINT = os.getenv("LOCAL_S3_ENDPOINT", "http://localhost:9000")

_S3_CLIENT_LOCK = Lock()
_S3_CLIENT: S3Client | None = None
_EFFECTIVE_ENDPOINT: str | None = None


@cache
def _s3_cache() -> Cache:
    """Get the RSS feed cache instance."""
    return Cache(".cache/s3")


def retry(attempts: int = 3, backoff_base: int = 2):
    """Decorator to retry a function with exponential backoff on failure."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            label = func.__name__
            last_exception = None
            for i in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if i < attempts:
                        wait = backoff_base**i  # 1s, 2s, 4s...
                        print(f"{label} attempt {i}/{attempts} failed. Wait {wait}s...")
                        time.sleep(wait)
                    else:
                        print(f"{label} failed all {attempts} attempts")

            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator


def _build_upload_extra_args(file_path: str, metadata_dict: dict | None) -> dict:
    """Build the ExtraArgs dict for a boto3 upload_file call."""
    extra_args: dict = {"ACL": "public-read"}
    if metadata_dict is not None:
        extra_args["Metadata"] = metadata_dict
    content_type, _ = mimetypes.guess_type(file_path)
    extra_args["ContentType"] = content_type or "application/octet-stream"
    return extra_args


def _make_upload_callback(
    callback: Callback, file_size: int
) -> "Callable[[int], None]":
    """Wrap a progress Callback in a thread-safe boto3-compatible callable."""
    lock = Lock()
    bytes_transferred = [0]

    def _cb(bytes_chunk: int) -> None:
        with lock:
            bytes_transferred[0] += bytes_chunk
            callback(bytes_transferred[0], file_size)

    return _cb


def _is_endpoint_reachable(url: str, timeout: float = 2.0) -> bool:
    """Return True if an actual S3 API call succeeds against the endpoint.

    A plain HTTP GET (or TCP probe) is not sufficient — a reverse proxy may
    return 200 for GET / while the underlying S3 backend is still unreachable,
    causing every real S3 operation to get a 502 Bad Gateway.  We probe with
    list_buckets() so the check exercises the same code-path as normal usage.
    """
    try:
        cfg = Config(
            signature_version="s3v4",
            connect_timeout=timeout,
            read_timeout=timeout,
            retries={"max_attempts": 1},
        )
        client = boto3.client(
            "s3",
            aws_access_key_id=S3_USERNAME,
            aws_secret_access_key=S3_SECRET_KEY,
            endpoint_url=url,
            config=cfg,
            region_name=S3_REGION,
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
    extra_args: dict
    boto_callback: Callable | None = None


def _do_s3_upload(spec: _UploadSpec) -> None:
    """Execute the actual S3 multipart upload via boto3."""
    transfer_config = TransferConfig(
        max_concurrency=10,
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


def _sync_upload_cache(bucket: str, key: str, metadata_dict: dict | None) -> None:
    """Update the local S3 metadata cache after an upload."""
    cache_key = f"s3_metadata:{bucket}:{key}"
    if metadata_dict is not None:
        _s3_cache().set(cache_key, metadata_dict)
    else:
        _s3_cache().delete(cache_key)


def _get_effective_s3_endpoint() -> str:
    """Resolve the endpoint boto3 should talk to."""
    global _EFFECTIVE_ENDPOINT

    if _EFFECTIVE_ENDPOINT is not None:
        return _EFFECTIVE_ENDPOINT

    # Prefer local endpoint if it's reachable.
    if _LOCAL_S3_ENDPOINT and _is_endpoint_reachable(_LOCAL_S3_ENDPOINT):
        _EFFECTIVE_ENDPOINT = _LOCAL_S3_ENDPOINT
    else:
        _EFFECTIVE_ENDPOINT = S3_ENDPOINT

    return _EFFECTIVE_ENDPOINT


def get_s3_client() -> S3Client:
    """Get a cached S3 client."""
    global _S3_CLIENT

    if _S3_CLIENT is not None:
        return _S3_CLIENT

    with _S3_CLIENT_LOCK:
        if _S3_CLIENT is not None:
            return _S3_CLIENT

        _S3_CLIENT = cast(S3Client, _build_s3_client())
        return _S3_CLIENT


def _build_s3_client() -> S3Client:
    """Construct a new boto3 S3 client (not cached).

    Exposed as a helper so client construction can be replaced or mocked
    independently of the caching layer in `get_s3_client()`.
    """
    session = boto3.session.Session()

    cfg = Config(
        signature_version="s3v4",
        connect_timeout=15,
        read_timeout=120,
        retries={"max_attempts": 5},
    )

    client = session.client(
        service_name="s3",
        aws_access_key_id=S3_USERNAME,
        aws_secret_access_key=S3_SECRET_KEY,
        # Use local shortcut endpoint when available; keep S3_ENDPOINT as public.
        endpoint_url=_get_effective_s3_endpoint(),
        config=cfg,
        region_name=S3_REGION,
    )

    return cast(S3Client, client)


def download_file(bucket: str, key: str, download_path: Path) -> None:
    """Download file using authenticated S3 client"""
    client = get_s3_client()
    response = client.get_object(Bucket=bucket, Key=key)

    with open(download_path, "wb") as f:
        for chunk in response["Body"].iter_chunks():
            f.write(chunk)


@retry(attempts=3, backoff_base=2)
def upload_file(
    bucket: str,
    key: str,
    file_path: Path,
    options: dict | MediaMetadata | None = None,
) -> str | None:
    """Upload a file to S3.

    The `options` argument may be one of:
      - `None` (no metadata or callback)
      - a `MediaMetadata` instance (metadata only)
      - a `dict` with optional keys `metadata` and `callback`
    """
    _file_path = file_path if isinstance(file_path, str) else file_path.as_posix()
    assert os.path.exists(_file_path), f"Local file not found: {file_path}"

    metadata = None
    callback = None
    if isinstance(options, dict):
        metadata = options.get("metadata")
        callback = options.get("callback")
    elif options is not None and not isinstance(options, dict):
        # Treat as metadata instance
        metadata = options

    metadata_dict = metadata.to_dict() if metadata is not None else None
    boto_callback = (
        _make_upload_callback(callback, os.path.getsize(_file_path))
        if callback is not None
        else None
    )

    spec = _UploadSpec(
        bucket=bucket,
        key=key,
        file_path=_file_path,
        extra_args=_build_upload_extra_args(_file_path, metadata_dict),
        boto_callback=boto_callback,
    )
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
    _file_path = file_path if isinstance(file_path, str) else file_path.as_posix()
    assert os.path.exists(_file_path), f"Local file not found: {file_path}"
    metadata_dict = metadata.to_dict() if metadata is not None else None

    spec = _UploadSpec(
        bucket=bucket,
        key=key,
        file_path=_file_path,
        extra_args=_build_upload_extra_args(_file_path, metadata_dict),
        boto_callback=None,
    )
    _do_s3_upload(spec)
    _sync_upload_cache(bucket, key, metadata_dict)
    return urljoin(S3_ENDPOINT, Path(bucket, key).as_posix())


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
    client.copy_object(
        Bucket=bucket, Key=new_key, CopySource=copy_source, MetadataDirective="COPY"
    )
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


def _get_file_map(bucket: str, prefix: str, without_extensions=True) -> dict:
    # Normalize prefix - add trailing slash for directory listing with delimiter
    prefix = prefix.lstrip(".")
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    cache_key = f"s3_file_map:{bucket}:{prefix}:{without_extensions}"
    cached_map = _s3_cache().get(cache_key)
    if cached_map is not None:
        return cached_map

    file_list: dict = {}
    for obj in _iterate_s3_objects(bucket, prefix):
        key = obj.get("Key", "")
        file_name = Path(key).name

        if without_extensions:
            file_name = Path(file_name).with_suffix("").as_posix()

        etag = obj.get("ETag", "").strip('"')[:32]
        file_list[file_name] = etag

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


def get_file_list(bucket: str, prefix: str, without_extensions=False) -> list[str]:
    prefix = prefix.lstrip(".").rstrip("/")
    file_map = _get_file_map(bucket, prefix, False)

    file_list = list(file_map.keys())
    if without_extensions:
        file_list = _remove_file_extensions(file_list)

    return file_list


def exists(bucket: str, prefix: str, extension_agnostic=True) -> str | None:
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
