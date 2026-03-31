from datetime import datetime, timezone, timedelta
from diskcache import Cache
from pathlib import Path
from typing import Any

import tempfile
import hashlib
import pickle
import base64
import json
import sys
import os
import re

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.files.s3 import (
    delete_file,
    download_file,
    exists,
    upload_file,
    upload_cache_file,
    get_s3_client,
)
from src.models import CacheMetadata


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

    def __init__(self, directory: str, s3_prefix: str):
        self.local_cache = Cache(directory)
        self.s3_prefix = s3_prefix.strip("/")
        self.bucket = "cache"

    def _get_s3_path(self, key: str) -> str:
        """Generate S3 path: <prefix>/<group>/<encoded>.pickle"""
        # Group by first token before ':' for human-friendly structure
        group = re.sub(r"[^A-Za-z0-9_\-]", "_", key.split(":", 1)[0] or "misc")

        # Encode key - use hash for long/unsafe keys
        encoded = base64.urlsafe_b64encode(key.encode()).decode().rstrip("=")
        if len(encoded) > self._MAX_ENCODED_LENGTH or not self._S3_SAFE_RE.match(
            encoded
        ):
            encoded = hashlib.sha256(key.encode()).hexdigest()

        return f"{self.s3_prefix}/{group}/{encoded}.pickle"

    def _check_expiration(self, key: str, s3_path: str) -> CacheMetadata | None:
        """Check if S3 cache entry is expired. Returns metadata if valid, None if expired."""
        try:
            client = get_s3_client()
            head = client.head_object(Bucket=self.bucket, Key=s3_path)

            # Normalize metadata from S3 to a form CacheMetadata can validate.
            raw_meta = head.get("Metadata", {}) or {}
            norm_meta: dict = {}

            # Older uploads may store an 'mtime' (epoch seconds). Convert it.
            if "created_at" in raw_meta:
                norm_meta["created_at"] = raw_meta["created_at"]
            elif "mtime" in raw_meta:
                try:
                    mtime_val = float(raw_meta["mtime"])
                    norm_meta["created_at"] = datetime.fromtimestamp(
                        mtime_val, timezone.utc
                    ).isoformat()
                except Exception:
                    # Fall back to raw metadata; validation will handle errors
                    pass

            if "expires_at" in raw_meta:
                norm_meta["expires_at"] = raw_meta["expires_at"]
            if "uploader" in raw_meta:
                norm_meta["uploader"] = raw_meta["uploader"]

            metadata = CacheMetadata.model_validate(norm_meta or raw_meta)

            if (
                metadata.expires_at
                and datetime.now(timezone.utc) >= metadata.expires_at
            ):
                print(f"S3 cache expired for {key}")
                self.delete(key)
                return None
            return metadata
        except Exception as e:
            print(f"WARNING: Failed to check S3 expiration for {key}: {e}")
            return None

    def get(self, key: str, default: Any = None) -> Any:
        # Check local cache first (fast path)
        value = self.local_cache.get(key)
        if value is not None:
            return value

        # Check S3 cache (best-effort - involves network calls)
        s3_path = self._get_s3_path(key)
        try:
            if not exists(self.bucket, s3_path, False):
                return default

            # Check expiration
            metadata = self._check_expiration(key, s3_path)
            if metadata is None and exists(self.bucket, s3_path, False):
                # Expired or metadata check failed, but not deleted - continue anyway
                metadata = CacheMetadata(created_at=datetime.now(timezone.utc))
            elif metadata is None:
                return default

            # Download and cache locally
            fd, tmp_str = tempfile.mkstemp(suffix=".pickle")
            tmp_path = Path(tmp_str)
            try:
                os.close(fd)
                download_file(self.bucket, s3_path, tmp_path)
                with open(tmp_path, "rb") as f:
                    value = pickle.load(f)

                # Calculate remaining TTL
                expire_seconds = None
                if metadata.expires_at:
                    remaining = (
                        metadata.expires_at - datetime.now(timezone.utc)
                    ).total_seconds()
                    expire_seconds = int(remaining) if remaining > 0 else None

                self.local_cache.set(key, value, expire=expire_seconds)
                return value
            finally:
                tmp_path.unlink(missing_ok=True)
        except Exception as e:
            print(f"WARNING: S3 cache read failed for {key}: {e}")

        return default

    def set(self, key: str, value: Any, expire: int | None = None) -> None:
        # Write to local cache
        self.local_cache.set(key, value, expire=expire)

        # Write to S3 cache (best-effort)
        try:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=expire)
                if expire
                else None
            )
            metadata = CacheMetadata(
                created_at=datetime.now(timezone.utc), expires_at=expires_at
            )

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir) / "data.pickle"
                with open(temp_path, "wb") as f:
                    pickle.dump(value, f)
                upload_cache_file(
                    self.bucket, self._get_s3_path(key), temp_path, metadata
                )
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
