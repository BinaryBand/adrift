from __future__ import annotations

from dataclasses import dataclass

from src.ports import (
    ReadOnlySecretStorePort,
    SecretProviderPort,
    SecretStorePort,
    require_secrets,
)

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


def describe_managed_secret(key: str) -> ManagedSecretField | None:
    return next((field for field in MANAGED_S3_FIELDS if field.key == key), None)


def is_writable_secret_store(store: ReadOnlySecretStorePort | SecretStorePort) -> bool:
    return isinstance(store, SecretStorePort)


def _state_source_and_value(
    key: str,
    store: ReadOnlySecretStorePort | SecretStorePort,
    provider: SecretProviderPort,
    provider_name: str,
) -> tuple[str, str]:
    if provider_name == "env" and store.has(key):
        return ".env", store.get(key, "")

    value = provider.get(key, "")
    if not value:
        return "missing", ""
    if provider_name == "env":
        return "environment", value
    return f"{provider_name}/env", value


def _require_writable_store(store: ReadOnlySecretStorePort | SecretStorePort) -> SecretStorePort:
    if isinstance(store, SecretStorePort):
        return store
    raise RuntimeError("Selected secret backend is read-only and cannot be edited")


def collect_secret_states(
    store: ReadOnlySecretStorePort | SecretStorePort,
    provider: SecretProviderPort,
    *,
    provider_name: str = "env",
) -> list[ManagedSecretState]:
    states: list[ManagedSecretState] = []
    for field in MANAGED_S3_FIELDS:
        source, value = _state_source_and_value(field.key, store, provider, provider_name)
        states.append(ManagedSecretState(field=field, value=value, source=source))
    return states


def set_secret_value(
    store: ReadOnlySecretStorePort | SecretStorePort, key: str, value: str
) -> None:
    writable_store = _require_writable_store(store)
    writable_store.set(key, value)
    writable_store.save()


def delete_secret_value(store: ReadOnlySecretStorePort | SecretStorePort, key: str) -> None:
    writable_store = _require_writable_store(store)
    writable_store.delete(key)
    writable_store.save()


def validate_required_secret_values(provider: SecretProviderPort) -> dict[str, str]:
    return require_secrets(provider, MANAGED_S3_KEYS)


def validate_s3_connection(provider: SecretProviderPort) -> None:
    from src.files.s3 import validate_s3_provider

    validate_s3_provider(provider, check_endpoint=True)
