"""Local filesystem storage adapter.

Storage root is a plain directory tree: <root>/<bucket>/<key>. Whatever is
mounted at <root> (e.g. an rclone mount) is an infra concern outside this
adapter's responsibility -- it just does ordinary file I/O.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from pydantic import ValidationError

from adrift.core.models import MediaMetadata, S3Metadata
from adrift.core.models.storage_options import UploadOptions
from adrift.core.util.progress import Callback

_METADATA_SUFFIX = ".meta.json"
_CHUNK_SIZE = 1024 * 1024
_UPLOAD_OPTIONS_ERRORS = (ValidationError, TypeError, ValueError)
_METADATA_VALIDATE_ERRORS = (ValidationError, TypeError, ValueError)


class LocalFilesystemStorage:
    """Filesystem-backed implementation of StoragePort."""

    def __init__(self, root: Path) -> None:
        """Initialize the storage adapter with the given root directory."""
        self.root = root

    def upload_file(
        self,
        bucket_key: tuple[str, str],
        file_path: Path,
        options: UploadOptions | S3Metadata | dict[str, Any] | None = None,
    ) -> str | None:
        """Upload a local file to storage and return the public URL."""
        bucket, key = bucket_key
        if not file_path.exists():
            msg = f"Local file not found: {file_path}"
            raise FileNotFoundError(msg)

        metadata, callback = _extract_upload_options(options)
        dest = self._object_path(bucket, key)
        _atomic_copy(file_path, dest, callback)
        if metadata is not None:
            _atomic_write_json(self._sidecar_path(bucket, key), metadata.to_dict())

        return self._build_url(key)

    def exists(self, bucket: str, prefix: str, *, extension_agnostic: bool = True) -> str | None:
        """Check if a file exists under the given prefix and return its name."""
        prefix = prefix.lstrip(".").rstrip("/")
        path = Path(prefix)
        parent_dir = path.parent.as_posix()
        if parent_dir == ".":
            parent_dir = ""
        identifier = path.stem if extension_agnostic else path.name

        for name in self.get_file_list(bucket, parent_dir, without_extensions=False):
            if _identifier_matches(name, identifier, extension_agnostic):
                return name
        return None

    def get_file_list(
        self, bucket: str, prefix: str, *, without_extensions: bool = False
    ) -> list[str]:
        """Return sorted list of file names under the given prefix."""
        prefix = prefix.lstrip(".").rstrip("/")
        directory = self._object_path(bucket, prefix) if prefix else self.root / bucket
        if not directory.is_dir():
            return []

        names = [
            entry.name
            for entry in directory.iterdir()
            if entry.is_file() and not entry.name.endswith(_METADATA_SUFFIX)
        ]
        if without_extensions:
            names = [Path(name).with_suffix("").as_posix() for name in names]
        return sorted(names)

    def get_public_urls(self, bucket: str, prefix: str) -> list[str]:
        """Return public URLs for all files under the given prefix."""
        file_list = self.get_file_list(bucket, prefix)
        return [self._build_url(f"{prefix}/{name}" if prefix else name) for name in file_list]

    def get_metadata(self, bucket: str, key: str) -> MediaMetadata | None:
        """Return validated media metadata for the given object, or None."""
        try:
            raw = json.loads(self._sidecar_path(bucket, key).read_text())
        except (OSError, json.JSONDecodeError):
            return None
        try:
            return MediaMetadata.model_validate(raw)
        except _METADATA_VALIDATE_ERRORS:
            return None

    def delete(self, bucket: str, key: str) -> None:
        """Delete a file and its metadata sidecar from storage."""
        self._object_path(bucket, key).unlink(missing_ok=True)
        self._sidecar_path(bucket, key).unlink(missing_ok=True)

    def _object_path(self, bucket: str, key: str) -> Path:
        _reject_traversal(bucket, key)
        return self.root / bucket / key

    def _sidecar_path(self, bucket: str, key: str) -> Path:
        return self._object_path(bucket, f"{key}{_METADATA_SUFFIX}")

    def _build_url(self, key: str) -> str:
        # RSS_BASE_URL: base URL for RSS enclosure links; required wherever
        # feeds are generated -- there is no fallback endpoint.
        rss_base_url = os.getenv("RSS_BASE_URL", "")

        if not rss_base_url:
            msg = "RSS_BASE_URL must be set to build public storage URLs"
            raise RuntimeError(msg)
        return urljoin(rss_base_url, key)


def _reject_traversal(*parts: str) -> None:
    for part in parts:
        if ".." in Path(part).parts:
            msg = f"Path traversal is not allowed: {part!r}"
            raise ValueError(msg)


def _identifier_matches(name: str, identifier: str, extension_agnostic: bool) -> bool:  # noqa: FBT001
    if extension_agnostic:
        return Path(name).with_suffix("").as_posix() == identifier
    return name == identifier


def _atomic_copy(src: Path, dest: Path, callback: Callback | None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = src.stat().st_size
    transferred = 0
    fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as tmp_file, src.open("rb") as src_file:
            while chunk := src_file.read(_CHUNK_SIZE):
                tmp_file.write(chunk)
                transferred += len(chunk)
                if callback is not None:
                    callback(transferred, total)
        Path(tmp_name).replace(dest)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _atomic_write_json(path: Path, data: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as tmp_file:
            json.dump(data, tmp_file)
        Path(tmp_name).replace(path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


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
        opts = UploadOptions.model_validate(options)
    except _UPLOAD_OPTIONS_ERRORS:
        return None, None
    else:
        return opts.metadata, opts.callback


__all__ = ["LocalFilesystemStorage"]
