from __future__ import annotations

import logging
import mimetypes
import time
from functools import wraps
from threading import Lock
from typing import TYPE_CHECKING, Any, Callable, ParamSpec, TypeVar

import boto3
from botocore.client import Config

from src.ports import SecretProviderPort, require_secrets
from src.utils.progress import Callback

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
else:
    S3Client = Any

_REQUIRED_S3_KEYS = ("S3_USERNAME", "S3_SECRET_KEY", "S3_ENDPOINT", "S3_REGION")
logger = logging.getLogger(__name__)

_P = ParamSpec("_P")
_T = TypeVar("_T")


def retry(
    attempts: int = 3, backoff_base: int = 2
) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    """Decorator to retry a function with exponential backoff on failure."""

    def decorator(func: Callable[_P, _T]) -> Callable[_P, _T]:
        return _make_retry_wrapper(func, attempts, backoff_base)

    return decorator


def _make_retry_wrapper(
    func: Callable[_P, _T], attempts: int, backoff_base: int
) -> Callable[_P, _T]:
    @wraps(func)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        label = getattr(func, "__name__", repr(func))
        last_exception: Exception | None = None
        for i in range(1, attempts + 1):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                last_exception = exc
                if i < attempts:
                    wait = backoff_base**i
                    logger.warning("%s attempt %d/%d failed. Wait %ss...", label, i, attempts, wait)
                    time.sleep(wait)
                else:
                    logger.error("%s failed all %d attempts", label, attempts)

        if last_exception is None:
            raise RuntimeError(f"{label} failed after {attempts} attempts")
        raise last_exception

    return wrapper


def _build_upload_extra_args(
    file_path: str, metadata_dict: dict[str, str] | None
) -> dict[str, Any]:
    extra_args: dict[str, Any] = {"ACL": "public-read"}
    if metadata_dict is not None:
        extra_args["Metadata"] = metadata_dict
    content_type, _ = mimetypes.guess_type(file_path)
    extra_args["ContentType"] = content_type or "application/octet-stream"
    return extra_args


def _make_upload_callback(callback: Callback, file_size: int) -> Callable[[int], None]:
    lock = Lock()
    bytes_transferred = [0]

    def _cb(bytes_chunk: int) -> None:
        with lock:
            bytes_transferred[0] += bytes_chunk
            callback(bytes_transferred[0], file_size)

    return _cb


def _make_boto_config(
    connect_timeout: float = 15, read_timeout: float = 120, max_attempts: int = 5
) -> Config:
    return Config(
        signature_version="s3v4",
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        retries={"max_attempts": max_attempts},
    )


def _is_endpoint_reachable_with_provider(
    url: str,
    provider: SecretProviderPort,
    timeout: float = 2.0,
) -> bool:
    try:
        _build_s3_probe_client(url, provider, timeout).list_buckets()
    except Exception:
        return False
    return True


def _build_s3_probe_client(
    url: str,
    provider: SecretProviderPort,
    timeout: float,
) -> S3Client:
    values = require_secrets(provider, _REQUIRED_S3_KEYS)
    cfg = _make_boto_config(connect_timeout=timeout, read_timeout=timeout, max_attempts=1)
    boto3_factory: Callable[..., Any] = boto3.client
    return boto3_factory(
        "s3",
        aws_access_key_id=values["S3_USERNAME"],
        aws_secret_access_key=values["S3_SECRET_KEY"],
        endpoint_url=url,
        config=cfg,
        region_name=values["S3_REGION"],
    )


__all__ = [
    "retry",
    "_make_retry_wrapper",
    "_build_upload_extra_args",
    "_make_upload_callback",
    "_make_boto_config",
    "_is_endpoint_reachable_with_provider",
    "_build_s3_probe_client",
]
