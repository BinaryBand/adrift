from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretProviderPort(Protocol):
    """Port for reading string secrets/config values by key."""

    def get(self, key: str, default: str = "") -> str: ...


@runtime_checkable
class ReadOnlySecretStorePort(Protocol):
    """Port for listing managed secret values without mutation support."""

    def get(self, key: str, default: str = "") -> str: ...

    def has(self, key: str) -> bool: ...

    def items(self) -> Mapping[str, str]: ...


@runtime_checkable
class SecretStorePort(ReadOnlySecretStorePort, Protocol):
    """Port for listing and persisting managed secret values."""

    def set(self, key: str, value: str) -> None: ...

    def delete(self, key: str) -> None: ...

    def save(self) -> None: ...


def require_secrets(provider: SecretProviderPort, keys: Sequence[str]) -> dict[str, str]:
    """Return required secret values or raise when any are missing."""
    values = {key: provider.get(key, "") for key in keys}
    missing = [key for key, value in values.items() if _is_missing_or_placeholder(key, value)]
    if missing:
        raise RuntimeError(f"Missing required S3 environment variables: {', '.join(missing)}")
    return values


def _is_missing_or_placeholder(key: str, value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return True
    # Catch unresolved templates such as S3_REGION, $S3_REGION, or ${S3_REGION}.
    return stripped in {key, f"${key}", f"${{{key}}}"}
