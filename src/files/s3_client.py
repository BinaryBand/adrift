# Thin re-export shim for S3 client related symbols

from src.files.s3 import (
    S3Service,
    _default_s3_service,
    _default_s3_service_lock,
    download_file,
    get_effective_s3_endpoint,
    get_s3_client,
    get_s3_service,
    register_s3_service,
    require_s3_env,
    reset_secret_provider,
    set_secret_provider,
    validate_s3_provider,
)

__all__ = [
    "S3Service",
    "register_s3_service",
    "get_s3_service",
    "set_secret_provider",
    "reset_secret_provider",
    "require_s3_env",
    "validate_s3_provider",
    "get_effective_s3_endpoint",
    "get_s3_client",
    "download_file",
    "_default_s3_service",
    "_default_s3_service_lock",
]
