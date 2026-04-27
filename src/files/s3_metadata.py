from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
else:
    S3Client = Any


def _fetch_head_metadata(client: S3Client, bucket: str, key: str) -> dict[str, str] | None:
    try:
        head_response = client.head_object(Bucket=bucket, Key=key)
    except Exception:
        return None
    raw_meta = head_response.get("Metadata", {})
    if not isinstance(raw_meta, dict):
        return {}
    try:
        return {str(k): str(v) for k, v in raw_meta.items()}
    except Exception:
        return {}


__all__ = ["_fetch_head_metadata"]
