# noqa: F841,F821
"""StoragePort protocol — abstraction for storage backend (S3, local disk, etc).

This protocol makes the storage implementation swappable and testable.
Production: S3Service implements this via S3Adapter.
Testing: InMemoryStorage or LocalStorageAdapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class UploadRequest:
    """Request parameters for uploading a file to storage."""

    bucket: str
    key: str
    path: Path
    metadata: dict[str, str] | None = None


class StoragePort(Protocol):
    """Protocol for storage operations.

    Implementations provide upload, download, existence checks, and listing.
    This abstraction allows swapping S3 for local disk or GCS without changing
    callers (e.g., the download pipeline).
    """

    def upload(self, request: UploadRequest) -> str:  # noqa: F841
        """Upload a file to storage.

        Args:
            request: UploadRequest with bucket, key, path, and optional metadata

        Returns:
            The full URI/path of the uploaded object

        Raises:
            StorageError if upload fails
        """
        ...

    def download(self, bucket: str, key: str, dest: Path) -> None:  # noqa: F841
        """Download a file from storage.

        Args:
            bucket: Storage bucket/container name
            key: Object key/path within the bucket
            dest: Local destination file path

        Raises:
            StorageError if download fails
        """
        ...

    def exists(self, bucket: str, prefix: str) -> bool:  # noqa: F841
        """Check if an object or prefix exists.

        Args:
            bucket: Storage bucket/container name
            prefix: Object key or key prefix to check

        Returns:
            True if the key or any key with this prefix exists

        Raises:
            StorageError if the check fails
        """
        ...

    def list_keys(self, bucket: str, prefix: str) -> list[str]:  # noqa: F841
        """List all object keys under a prefix.

        Args:
            bucket: Storage bucket/container name
            prefix: Key prefix to list under

        Returns:
            List of object keys matching the prefix

        Raises:
            StorageError if listing fails
        """
        ...


__all__ = [
    "StoragePort",
    "UploadRequest",
]
