from __future__ import annotations

from dataclasses import dataclass

from src.ports.secrets import SecretProviderPort, SecretStorePort, require_secrets

MANAGED_S3_KEYS = (
    "S3_USERNAME",
    "S3_SECRET_KEY",
    "S3_ENDPOINT",
    "S3_REGION",
)


@dataclass(frozen=True)
class ManagedSecretField:
    key: str
    label: str
    sensitive: bool = False
    description: str = ""


@dataclass(frozen=True)
class ManagedSecretState:
    field: ManagedSecretField
    value: str
    source: str

    @property
    def masked_value(self) -> str:
        if not self.value:
            return "<missing>"
        if not self.field.sensitive:
            return self.value
        if len(self.value) <= 4:
            return "*" * len(self.value)
        return f"{'*' * (len(self.value) - 4)}{self.value[-4:]}"


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


def collect_secret_states(
    store: SecretStorePort,
    provider: SecretProviderPort,
) -> list[ManagedSecretState]:
    states: list[ManagedSecretState] = []
    for field in MANAGED_S3_FIELDS:
        if store.has(field.key):
            source = ".env"
            value = store.get(field.key, "")
        else:
            value = provider.get(field.key, "")
            source = "environment" if value else "missing"
        states.append(ManagedSecretState(field=field, value=value, source=source))
    return states


def set_secret_value(store: SecretStorePort, key: str, value: str) -> None:
    store.set(key, value)
    store.save()


def delete_secret_value(store: SecretStorePort, key: str) -> None:
    store.delete(key)
    store.save()


def validate_required_secret_values(provider: SecretProviderPort) -> dict[str, str]:
    return require_secrets(provider, MANAGED_S3_KEYS)


def validate_s3_connection(provider: SecretProviderPort) -> None:
    from src.files.s3 import validate_s3_provider

    validate_s3_provider(provider, check_endpoint=True)
