from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from adrift.core.models import S3Metadata
    from adrift.core.util.progress import Callback


class UploadOptions(BaseModel):
    """Options model for `StoragePort.upload_file`.

    Uses arbitrary types to allow passing a `Callback` callable.
    """

    metadata: S3Metadata | None = None
    callback: Callback | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


__all__ = ["UploadOptions"]
