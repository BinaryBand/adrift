# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedFunction=false

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, Callable, Iterator
from urllib.parse import urljoin

import boto3

from src.files.s3_cache import _s3_cache
from src.files.s3_listing import (
    _identifier_matches as _listing_identifier_matches,
)
from src.files.s3_listing import (
    _remove_file_extensions as _listing_remove_file_extensions,
)
from src.files.s3_metadata import _fetch_head_metadata as _metadata_fetch_head_metadata
from src.files.s3_types import UploadOptions, _UploadSpec
from src.files.s3_upload import (
    _do_s3_upload as _upload_with_client,
)
from src.files.s3_upload import (
    _prepare_upload_spec,
)
from src.files.s3_utils import (
    _is_endpoint_reachable_with_provider,
    _make_boto_config,
    retry,
)

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
    from mypy_boto3_s3.type_defs import CopySourceTypeDef
else:
    S3Client = Any
    CopySourceTypeDef = dict[str, Any]

from src.adapters import get_secret_provider_adapter
from src.models import CacheMetadata, MediaMetadata
from src.ports import SecretProviderPort, require_secrets

_REQUIRED_S3_KEYS = ("S3_USERNAME", "S3_SECRET_KEY", "S3_ENDPOINT", "S3_REGION")

_secret_provider: SecretProviderPort = get_secret_provider_adapter()

S3_ENDPOINT = _secret_provider.get("S3_ENDPOINT", "")


# Injectable S3 service ----------------------------------------------------
class S3Service:
    """Encapsulate S3 client construction and provide an injectable service.

    This is intentionally lightweight: it owns a cached boto3 client and the
    secret provider to use when building clients. Callers may register a
    different service with `register_s3_service()` for testing or alternate
    behavior.
    """

    def __init__(self, secret_provider: SecretProviderPort | None = None, **kwargs: Any) -> None:
        """Construct the service.

        Accepts optional keyword args for `session_factory` and `cache` to aid
        testing, but keeps a short explicit signature to satisfy the lizard
        parameter-count gate.
        """
        self.secret_provider = secret_provider or _secret_provider
        session_factory = kwargs.get("session_factory")
        cache = kwargs.get("cache")

        self._session_factory = session_factory or boto3.session.Session
        self._client_lock = Lock()
        self._client: S3Client | None = None
        self._effective_endpoint: str | None = None
        self.cache = cache if cache is not None else _s3_cache()

    @classmethod
    def from_env(cls, provider: SecretProviderPort | None = None, **kwargs: Any) -> "S3Service":
        return cls(provider or _secret_provider, **kwargs)

    def build_client(self) -> S3Client:
        """Construct a fresh boto3 S3 client using this service's secret provider."""
        session = self._session_factory()
        values = require_secrets(self.secret_provider, _REQUIRED_S3_KEYS)

        cfg = _make_boto_config()
        session_factory: Callable[..., Any] = session.client  # pyright: ignore[reportUnknownVariableType]

        return session_factory(
            "s3",
            aws_access_key_id=values["S3_USERNAME"],
            aws_secret_access_key=values["S3_SECRET_KEY"],
            endpoint_url=self.get_effective_endpoint(),
            config=cfg,
            region_name=values["S3_REGION"],
        )

    def get_client(self) -> S3Client:
        if self._client is not None:
            return self._client
        with self._client_lock:
            if self._client is not None:
                return self._client
            self._client = self.build_client()
            return self._client

    def _get_effective_endpoint(self) -> str:
        if self._effective_endpoint is not None:
            return self._effective_endpoint

        values = require_secrets(self.secret_provider, _REQUIRED_S3_KEYS)
        endpoint = values["S3_ENDPOINT"]

        # Prefer configured LOCAL_S3_ENDPOINT when reachable
        local_endpoint = _configured_local_s3_endpoint(self.secret_provider)
        if local_endpoint and _is_endpoint_reachable_with_provider(
            local_endpoint, self.secret_provider
        ):
            self._effective_endpoint = local_endpoint
        else:
            self._effective_endpoint = endpoint

        return self._effective_endpoint

    def get_effective_endpoint(self) -> str:
        """Public accessor for the effective endpoint used by this service."""
        return self._get_effective_endpoint()

    # -- Probe / client helpers ------------------------------------------------
    def build_probe_client(self, url: str, timeout: float) -> S3Client:
        values = require_secrets(self.secret_provider, _REQUIRED_S3_KEYS)
        cfg = _make_boto_config(connect_timeout=timeout, read_timeout=timeout, max_attempts=1)
        boto3_factory: Callable[..., Any] = boto3.client  # pyright: ignore[reportUnknownVariableType]
        return boto3_factory(
            "s3",
            aws_access_key_id=values["S3_USERNAME"],
            aws_secret_access_key=values["S3_SECRET_KEY"],
            endpoint_url=url,
            config=cfg,
            region_name=values["S3_REGION"],
        )

    def is_endpoint_reachable(self, url: str, timeout: float = 2.0) -> bool:
        try:
            self.build_probe_client(url, timeout).list_buckets()
        except Exception:
            return False
        return True

    # -- Cache helpers ---------------------------------------------------------
    def invalidate_file_map_cache(self, bucket: str, key: str) -> None:
        parent_dir = Path(key).parent.as_posix()
        if parent_dir == ".":
            parent_dir = ""
        if parent_dir and not parent_dir.endswith("/"):
            parent_dir += "/"
        for ext_agnostic in (True, False):
            cache_key = f"s3_file_map:{bucket}:{parent_dir}:{ext_agnostic}"
            self.cache.delete(cache_key)

    def sync_upload_cache(
        self, bucket: str, key: str, metadata_dict: dict[str, str] | None
    ) -> None:
        cache_key = f"s3_metadata:{bucket}:{key}"
        if metadata_dict is not None:
            self.cache.set(cache_key, metadata_dict)
        else:
            self.cache.delete(cache_key)
        self.invalidate_file_map_cache(bucket, key)

    def sync_copy_cache(self, bucket: str, source_key: str, dest_key: str) -> None:
        src_cache_key = f"s3_metadata:{bucket}:{source_key}"
        dst_cache_key = f"s3_metadata:{bucket}:{dest_key}"
        metadata = self.cache.get(src_cache_key)
        if metadata is None:
            client = self.get_client()
            metadata = self.fetch_head_metadata(client, bucket, dest_key)
        if metadata is not None:
            self.cache.set(dst_cache_key, metadata)

    def fetch_head_metadata(self, client: S3Client, bucket: str, key: str) -> dict[str, str] | None:
        return _metadata_fetch_head_metadata(client, bucket, key)

    def public_s3_url(self, bucket: str, key: str) -> str:
        return urljoin(
            self.secret_provider.get("S3_ENDPOINT", S3_ENDPOINT), Path(bucket, key).as_posix()
        )

    # -- Listing / map helpers -------------------------------------------------
    def build_file_map_from_iterator(
        self, bucket: str, prefix: str, without_extensions: bool
    ) -> dict[str, str]:
        file_list: dict[str, str] = {}
        for obj in self.iterate_s3_objects(bucket, prefix):
            key = obj.get("Key", "")
            file_name = Path(key).name

            if without_extensions:
                file_name = Path(file_name).with_suffix("").as_posix()

            etag = obj.get("ETag", "").strip('"')[:32]
            file_list[file_name] = etag

        return file_list

    def get_file_map(
        self, bucket: str, prefix: str, without_extensions: bool = True
    ) -> dict[str, str]:
        prefix = prefix.lstrip(".")
        if prefix and not prefix.endswith("/"):
            prefix += "/"

        cache_key = f"s3_file_map:{bucket}:{prefix}:{without_extensions}"
        cached_map = self.cache.get(cache_key)
        if cached_map is not None:
            return cached_map

        file_list = self.build_file_map_from_iterator(bucket, prefix, without_extensions)
        self.cache.set(cache_key, file_list, expire=300)
        return file_list

    def iterate_s3_objects(self, bucket: str, prefix: str) -> Iterator[Any]:
        s3: S3Client = self.get_client()
        paginator = s3.get_paginator("list_objects_v2")
        page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/")

        for page in page_iterator:
            for obj in page.get("Contents", {}):
                yield obj

    def _remove_file_extensions(self, file_names: list[str]) -> list[str]:
        return _listing_remove_file_extensions(file_names)

    def get_file_list(
        self, bucket: str, prefix: str, without_extensions: bool = False
    ) -> list[str]:
        prefix = prefix.lstrip(".").rstrip("/")
        file_map = self.get_file_map(bucket, prefix, False)

        file_list = list(file_map.keys())
        if without_extensions:
            file_list = self._remove_file_extensions(file_list)

        return file_list

    def get_s3_files(self, bucket: str, prefix: str) -> list[str]:
        from src.config import RSS_BASE_URL

        file_list = self.get_file_list(bucket, prefix)
        root_path = Path(bucket) / prefix
        base_url = RSS_BASE_URL or self.get_effective_endpoint()

        files: list[str] = []
        for file_key in file_list:
            filename = Path(file_key).name
            location = urljoin(base_url, (root_path / filename).as_posix())
            files.append(location)

        return files

    def exists(self, bucket: str, prefix: str, extension_agnostic: bool = True) -> str | None:
        prefix = prefix.lstrip(".").rstrip("/")
        key: Path = Path(prefix)

        parent_dir = key.parent.as_posix()
        if parent_dir == ".":
            parent_dir = ""

        identifier = key.stem if extension_agnostic else key.name
        file_list: list[str] = self.get_file_list(bucket, parent_dir, False)

        for f in file_list:
            if _identifier_matches(f, identifier, extension_agnostic):
                return f

        return None

    # -- Metadata / object operations -----------------------------------------
    def get_metadata(self, bucket: str, key: str) -> MediaMetadata | None:
        key = Path(key).as_posix()
        cache_key = f"s3_metadata:{bucket}:{key}"
        metadata = self.cache.get(cache_key)

        if metadata is None and self.exists(bucket, key) is not None:
            try:
                client: S3Client = self.get_client()
                head_response = client.head_object(Bucket=bucket, Key=key)
                metadata = head_response.get("Metadata", {})
                self.cache.set(cache_key, metadata)
            except Exception:
                pass

        try:
            return MediaMetadata.model_validate(metadata)
        except Exception:
            return None

    def set_metadata(self, bucket: str, key: str, metadata: MediaMetadata) -> None:
        key = Path(key).as_posix()
        metadata_dict = metadata.to_dict()

        client: S3Client = self.get_client()
        client.copy_object(
            Bucket=bucket,
            Key=key,
            CopySource={"Bucket": bucket, "Key": key},
            Metadata=metadata_dict,
            MetadataDirective="REPLACE",
            ACL="public-read",
        )

        cache_key = f"s3_metadata:{bucket}:{key}"
        self.cache.set(cache_key, metadata_dict)

    def delete_file(self, bucket: str, key: str) -> None:
        client: S3Client = self.get_client()
        client.delete_object(Bucket=bucket, Key=key)

        cache_key = f"s3_metadata:{bucket}:{key}"
        self.cache.delete(cache_key)
        self.invalidate_file_map_cache(bucket, key)

    def rename_file(self, bucket: str, old_key: str, new_key: str) -> None:
        if old_key == new_key:
            return

        client: S3Client = self.get_client()

        copy_source: CopySourceTypeDef = {"Bucket": bucket, "Key": old_key}
        client.copy_object(
            Bucket=bucket, Key=new_key, CopySource=copy_source, MetadataDirective="COPY"
        )
        client.delete_object(Bucket=bucket, Key=old_key)

        old_cache_key = f"s3_metadata:{bucket}:{old_key}"
        new_cache_key = f"s3_metadata:{bucket}:{new_key}"
        self.cache.set(new_cache_key, self.cache.get(old_cache_key))
        self.cache.delete(old_cache_key)
        self.invalidate_file_map_cache(bucket, old_key)
        self.invalidate_file_map_cache(bucket, new_key)

    def copy_file(self, bucket: str, source_key: str, dest_key: str) -> str | None:
        client: S3Client = self.get_client()
        copy_source: CopySourceTypeDef = {"Bucket": bucket, "Key": source_key}
        client.copy_object(
            Bucket=bucket,
            Key=dest_key,
            CopySource=copy_source,
            MetadataDirective="COPY",
            ACL="public-read",
        )
        self.sync_copy_cache(bucket, source_key, dest_key)
        return self.public_s3_url(bucket, dest_key)

    def do_s3_upload(self, spec: _UploadSpec) -> None:
        _upload_with_client(self.get_client(), spec)

    def upload_file(
        self,
        bucket_key: tuple[str, str],
        file_path: Path,
        options: UploadOptions | MediaMetadata | dict[str, Any] | None = None,
    ) -> str | None:
        bucket, key = bucket_key
        spec, metadata_dict = _prepare_upload_spec(bucket, key, file_path, options)
        self.do_s3_upload(spec)
        self.sync_upload_cache(bucket, key, metadata_dict)
        return urljoin(
            self.secret_provider.get("S3_ENDPOINT", S3_ENDPOINT), Path(bucket, key).as_posix()
        )

    def upload_cache_file(
        self,
        bucket_key: tuple[str, str],
        file_path: Path,
        metadata: CacheMetadata | None = None,
    ) -> str | None:
        bucket, key = bucket_key
        spec, metadata_dict = _prepare_upload_spec(bucket, key, file_path, metadata)
        self.do_s3_upload(spec)
        self.sync_upload_cache(bucket, key, metadata_dict)
        return urljoin(
            self.secret_provider.get("S3_ENDPOINT", S3_ENDPOINT), Path(bucket, key).as_posix()
        )

    def download_file(self, bucket: str, key: str, download_path: Path) -> None:
        client = self.get_client()
        response = client.get_object(Bucket=bucket, Key=key)

        with open(download_path, "wb") as f:
            for chunk in response["Body"].iter_chunks():
                f.write(chunk)


# Global default service registration --------------------------------------
_default_s3_service: S3Service | None = None
_default_s3_service_lock = Lock()


def register_s3_service(service: S3Service) -> None:
    """Register a global default `S3Service` instance (thread-safe)."""
    global _default_s3_service
    with _default_s3_service_lock:
        _default_s3_service = service


def get_s3_service() -> S3Service:
    """Return the registered `S3Service`, creating a default one from the
    environment if none is registered yet.
    """
    global _default_s3_service
    with _default_s3_service_lock:
        if _default_s3_service is None:
            _default_s3_service = S3Service.from_env()
        return _default_s3_service


def set_secret_provider(provider: SecretProviderPort) -> None:
    """Swap the secret provider port implementation used by this module."""
    global _secret_provider
    _secret_provider = provider
    # Re-create the default registered service so the new provider is used.
    register_s3_service(S3Service.from_env(provider))


def reset_secret_provider() -> None:
    """Restore default environment-backed secret provider."""
    set_secret_provider(get_secret_provider_adapter("env", enable_prompt_fallback=False))


def require_s3_env() -> tuple[str, str, str, str]:
    values = require_secrets(
        _secret_provider,
        _REQUIRED_S3_KEYS,
    )
    return (
        values["S3_USERNAME"],
        values["S3_SECRET_KEY"],
        values["S3_ENDPOINT"],
        values["S3_REGION"],
    )


def _configured_local_s3_endpoint(
    provider: SecretProviderPort | None = None,
) -> str | None:
    active_provider = provider or _secret_provider
    endpoint = active_provider.get("LOCAL_S3_ENDPOINT", "").strip()
    return endpoint or None


def validate_s3_provider(
    provider: SecretProviderPort | None = None,
    *,
    check_endpoint: bool,
) -> None:
    active_provider = provider or _secret_provider
    values = require_secrets(active_provider, _REQUIRED_S3_KEYS)
    if not check_endpoint:
        return
    local_endpoint = _configured_local_s3_endpoint(active_provider)
    if local_endpoint and _is_endpoint_reachable_with_provider(local_endpoint, active_provider):
        return
    endpoint = values["S3_ENDPOINT"]
    if _is_endpoint_reachable_with_provider(endpoint, active_provider):
        return
    raise RuntimeError(f"Unable to reach configured S3 endpoint: {endpoint}")


def _invalidate_file_map_cache(bucket: str, key: str) -> None:
    """Invalidate the file-map cache for the directory containing `key`.

    Called after any mutation (upload, rename, delete) so that the next call
    to `exists()` / `get_file_list()` re-lists the directory from S3 rather
    than returning a stale cached result.
    """
    return get_s3_service().invalidate_file_map_cache(bucket, key)


def _sync_upload_cache(bucket: str, key: str, metadata_dict: dict[str, str] | None) -> None:
    """Update the local S3 metadata cache after an upload."""
    return get_s3_service().sync_upload_cache(bucket, key, metadata_dict)


def get_effective_s3_endpoint() -> str:
    """Resolve the endpoint boto3 should talk to."""
    # Delegate to the registered service for endpoint resolution so that any
    # registered service's provider is consulted.
    return get_s3_service().get_effective_endpoint()


def get_s3_client() -> S3Client:
    """Get a cached S3 client."""
    # Use the registered service's client; this allows tests to register a
    # fake service and ensures a single place to control client construction.
    return get_s3_service().get_client()


@retry(attempts=5, backoff_base=2)
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
    options: UploadOptions | MediaMetadata | dict[str, Any] | None = None,
) -> str | None:
    """Upload a file to S3.

    The `options` argument may be one of:
      - `None` (no metadata or callback)
      - a `MediaMetadata` instance (metadata only)
      - an `UploadOptions` dict with optional keys `metadata` and `callback`
    """
    return get_s3_service().upload_file((bucket, key), file_path, options)


@retry(attempts=3, backoff_base=2)
def upload_cache_file(
    bucket: str,
    key: str,
    file_path: Path,
    metadata: CacheMetadata | None = None,
) -> str | None:
    return get_s3_service().upload_cache_file((bucket, key), file_path, metadata)


@retry(attempts=3, backoff_base=2)
def delete_file(bucket: str, key: str) -> None:
    return get_s3_service().delete_file(bucket, key)


def rename_file(bucket: str, old_key: str, new_key: str) -> None:
    return get_s3_service().rename_file(bucket, old_key, new_key)


@retry(attempts=3, backoff_base=2)
def copy_file(bucket: str, source_key: str, dest_key: str) -> str | None:
    """Copy an object within the same bucket and return its public URL.

    Updates the local S3 metadata cache to reflect the copied object when possible.
    """
    return get_s3_service().copy_file(bucket, source_key, dest_key)


def _sync_copy_cache(bucket: str, source_key: str, dest_key: str) -> None:
    return get_s3_service().sync_copy_cache(bucket, source_key, dest_key)


def _fetch_head_metadata(client: S3Client, bucket: str, key: str) -> dict[str, str] | None:
    return get_s3_service().fetch_head_metadata(client, bucket, key)


def _public_s3_url(bucket: str, key: str) -> str:
    return get_s3_service().public_s3_url(bucket, key)


def get_metadata(bucket: str, key: str) -> MediaMetadata | None:
    return get_s3_service().get_metadata(bucket, key)


def set_metadata(bucket: str, key: str, metadata: MediaMetadata) -> None:
    return get_s3_service().set_metadata(bucket, key, metadata)


def _build_file_map_from_iterator(
    bucket: str, prefix: str, without_extensions: bool
) -> dict[str, str]:
    """Build a file->etag map from the iterator that yields S3 objects.

    Extracted so pagination and mapping logic can be tested or swapped
    independently of the cache handling in `_get_file_map()`.
    """
    return get_s3_service().build_file_map_from_iterator(bucket, prefix, without_extensions)


def _get_file_map(bucket: str, prefix: str, without_extensions: bool = True) -> dict[str, str]:
    # Normalize prefix - add trailing slash for directory listing with delimiter
    prefix = prefix.lstrip(".")
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    return get_s3_service().get_file_map(bucket, prefix, without_extensions)


def _iterate_s3_objects(bucket: str, prefix: str) -> Iterator[Any]:
    """Yield object dicts for all objects under `bucket/prefix`.

    Extracted from `_get_file_map()` so pagination can be tested or swapped
    independently of the mapping/ETag logic.
    """
    yield from get_s3_service().iterate_s3_objects(bucket, prefix)


def _remove_file_extensions(file_names: list[str]) -> list[str]:
    return _listing_remove_file_extensions(file_names)


def get_file_list(bucket: str, prefix: str, without_extensions: bool = False) -> list[str]:
    return get_s3_service().get_file_list(bucket, prefix, without_extensions)


def get_s3_files(bucket: str, prefix: str) -> list[str]:
    return get_s3_service().get_s3_files(bucket, prefix)


def exists(bucket: str, prefix: str, extension_agnostic: bool = True) -> str | None:
    prefix = prefix.lstrip(".").rstrip("/")
    return get_s3_service().exists(bucket, prefix, extension_agnostic)


def _identifier_matches(name: str, identifier: str, extension_agnostic: bool) -> bool:
    return _listing_identifier_matches(name, identifier, extension_agnostic)
