from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ManagedSecretField:
    key: str
    label: str
    sensitive: bool = False
    description: str = ""


MANAGED_S3_FIELDS = (
    ManagedSecretField(
        key="S3_USERNAME",
        label="S3 username",
        description="Access key or username for the S3-compatible endpoint.",
    ),
    ManagedSecretField(
        key="S3_SECRET_KEY",
        label="S3 secret key",
        sensitive=True,
        description="Secret access key for the S3-compatible endpoint.",
    ),
    ManagedSecretField(
        key="S3_ENDPOINT",
        label="S3 endpoint",
        description="Primary public endpoint used for uploads and downloads.",
    ),
    ManagedSecretField(
        key="S3_REGION",
        label="S3 region",
        description="Region passed to the S3 client.",
    ),
)


def describe_managed_secret(key: str) -> ManagedSecretField | None:
    return next((field for field in MANAGED_S3_FIELDS if field.key == key), None)
