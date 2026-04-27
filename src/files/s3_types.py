from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict

from src.models import S3Metadata
from src.utils.progress import Callback


@dataclass
class _UploadSpec:
    bucket: str
    key: str
    file_path: str
    extra_args: dict[str, Any]
    boto_callback: Callable[[int], None] | None = None


class UploadOptions(BaseModel):
    """Options model for `upload_file`.

    Uses arbitrary types to allow passing a `Callback` callable.
    """

    metadata: S3Metadata | None = None
    callback: Callback | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


__all__ = ["_UploadSpec", "UploadOptions"]
