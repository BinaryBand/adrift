# Thin re-export shim for S3 types used across modules

from src.files.s3 import UploadOptions, _UploadSpec

__all__ = ["_UploadSpec", "UploadOptions"]
