import base64
import hashlib
import json
import os
import pickle
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from diskcache import Cache

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.files.s3 import (
    delete_file,
    download_file,
    exists,
    get_s3_client,
    upload_cache_file,
    upload_file,
)
from src.models import CacheMetadata

_PASSTHROUGH_META_KEYS = ("expires_at", "uploader")


def _resolve_created_at(raw_meta: dict[str, Any]) -> str | None:
    """Extract or convert a creation timestamp from raw S3 object metadata."""
    if "created_at" in raw_meta:
        return raw_meta["created_at"]
    try:
        return datetime.fromtimestamp(float(raw_meta["mtime"]), timezone.utc).isoformat()
    except Exception:
        return None


def _normalize_s3_meta(raw_meta: dict[str, Any]) -> dict[str, Any]:
    """Normalise S3 object metadata into a form CacheMetadata can validate."""
    norm = {k: raw_meta[k] for k in _PASSTHROUGH_META_KEYS if k in raw_meta}
    if created_at := _resolve_created_at(raw_meta):
        norm["created_at"] = created_at
    return norm or raw_meta


def _remaining_ttl(metadata: CacheMetadata) -> int | None:
    """Return remaining seconds until expiry, or None if no expiry is set."""
    if not metadata.expires_at:
        return None
    remaining = (metadata.expires_at - datetime.now(timezone.utc)).total_seconds()
    return int(remaining) if remaining > 0 else None


def read_s3_json_cache(cache_path: str, item_id: str) -> Any | None:
    """Read JSON data from S3 cache."""
    if not exists("cache", cache_path, False):
        return None

    fd, tmp_str = tempfile.mkstemp(suffix=".json")
    tmp_path = Path(tmp_str)
    try:
        os.close(fd)
        download_file("cache", cache_path, tmp_path)
        return json.loads(tmp_path.read_text(encoding="utf-8"))
    except Exception as e:
        delete_file("cache", cache_path)
        print(f"WARNING: Cache read failed for {item_id}: {e}")
        return None
    finally:
        tmp_path.unlink(missing_ok=True)


def write_s3_json_cache(cache_path: str, item_id: str, data: Any) -> None:
    """Write JSON data to S3 cache (best-effort)."""
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / f"{item_id}.json"
            temp_path.write_text(json.dumps(data), encoding="utf-8")
            upload_file("cache", cache_path, temp_path)
    except Exception as e:
        print(f"WARNING: Cache write failed for {item_id}: {e}")


class S3Cache:
    """A cache wrapper that uses local diskcache and S3 as a secondary layer.

    The mapping is:
      s3_key = <prefix>/<group>/<encoded>.<ext>

    Where:
    - group = first token before ':' (if present) else 'misc'
    - encoded = urlsafe-base64(utf8(key)) (padding stripped) if short enough,
               otherwise sha256(utf8(key)) for long keys
    """

    _S3_SAFE_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
    _MAX_ENCODED_LENGTH = 200
    _S3_REQUEST_DELAY = 0.1  # 100ms delay between S3 reads to avoid rate limiting

    def __init__(self, directory: str, s3_prefix: str):
        self.local_cache = Cache(directory)
        self.s3_prefix = s3_prefix.strip("/")
        self.bucket = "cache"
        self._last_s3_request_time = 0

    def _get_s3_path(self, key: str) -> str:
        """Generate S3 path: <prefix>/<group>/<encoded>.pickle"""
        # Group by first token before ':' for human-friendly structure
        group = re.sub(r"[^A-Za-z0-9_\-]", "_", key.split(":", 1)[0] or "misc")

        # Encode key - use hash for long/unsafe keys
        encoded = base64.urlsafe_b64encode(key.encode()).decode().rstrip("=")
        if len(encoded) > self._MAX_ENCODED_LENGTH or not self._S3_SAFE_RE.match(encoded):
            encoded = hashlib.sha256(key.encode()).hexdigest()

        return f"{self.s3_prefix}/{group}/{encoded}.pickle"

    def _check_expiration(self, key: str, s3_path: str) -> CacheMetadata | None:
        """Read S3 object metadata and return it if the entry has not expired."""
        try:
            client = get_s3_client()
            head = client.head_object(Bucket=self.bucket, Key=s3_path)
            metadata = CacheMetadata.model_validate(
                _normalize_s3_meta(head.get("Metadata", {}) or {})
            )
            if metadata.expires_at and datetime.now(timezone.utc) >= metadata.expires_at:
                print(f"S3 cache expired for {key}")
                self.delete(key)
                return None
            return metadata
        except Exception as e:
            print(f"WARNING: Failed to check S3 expiration for {key}: {e}")
            return None

    def _throttle_s3_request(self) -> None:
        """Enforce minimum delay between S3 requests to avoid rate limiting."""
        elapsed = time.time() - self._last_s3_request_time
        if elapsed < self._S3_REQUEST_DELAY:
            time.sleep(self._S3_REQUEST_DELAY - elapsed)
        self._last_s3_request_time = time.time()

    def _resolve_s3_metadata(self, key: str, s3_path: str) -> CacheMetadata | None:
        """Return valid metadata for an S3 entry, or None if absent/expired/deleted."""
        if not exists(self.bucket, s3_path, False):
            return None
        metadata = self._check_expiration(key, s3_path)
        if metadata is None and exists(self.bucket, s3_path, False):
            # Entry survived deletion (expiry check failed) – use a stub so fetch proceeds.
            return CacheMetadata(created_at=datetime.now(timezone.utc))
        return metadata

    def _download_from_s3(self, s3_path: str, key: str, metadata: CacheMetadata) -> Any | None:
        """Download, deserialize and populate local cache. Returns value or None."""
        self._throttle_s3_request()
        fd, tmp_str = tempfile.mkstemp(suffix=".pickle")
        tmp_path = Path(tmp_str)
        try:
            os.close(fd)
            download_file(self.bucket, s3_path, tmp_path)
            with open(tmp_path, "rb") as f:
                value = pickle.load(f)
            expire_seconds = _remaining_ttl(metadata)
            self.local_cache.set(key, value, expire=expire_seconds)
            return value
        finally:
            tmp_path.unlink(missing_ok=True)

    def get(self, key: str, default: Any = None) -> Any:
        # Fast path: local cache.
        value = self.local_cache.get(key)
        if value is not None:
            return value
        # Slow path: S3 (best-effort).
        s3_path = self._get_s3_path(key)
        try:
            metadata = self._resolve_s3_metadata(key, s3_path)
            if metadata is None:
                return default
            return self._download_from_s3(s3_path, key, metadata) or default
        except Exception as e:
            print(f"WARNING: S3 cache read failed for {key}: {e}")
        return default

    def _build_cache_metadata(self, expire: int | None) -> CacheMetadata:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expire) if expire else None
        return CacheMetadata(created_at=datetime.now(timezone.utc), expires_at=expires_at)

    def _upload_to_s3(self, key: str, value: Any, metadata: CacheMetadata) -> None:
        """Serialize value to a temp file then upload to S3."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "data.pickle"
            with open(temp_path, "wb") as f:
                pickle.dump(value, f)
            upload_cache_file(self.bucket, self._get_s3_path(key), temp_path, metadata)

    def set(self, key: str, value: Any, expire: int | None = None) -> None:
        self.local_cache.set(key, value, expire=expire)
        try:
            self._upload_to_s3(key, value, self._build_cache_metadata(expire))
        except Exception as e:
            print(f"WARNING: S3 cache write failed for {key}: {e}")

    def delete(self, key: str) -> None:
        self.local_cache.delete(key)
        try:
            s3_path = self._get_s3_path(key)
            if exists(self.bucket, s3_path, False):
                delete_file(self.bucket, s3_path)
        except Exception as e:
            print(f"WARNING: S3 cache delete failed for {key}: {e}")

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None
