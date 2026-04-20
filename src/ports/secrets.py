from collections.abc import Mapping, Sequence
from typing import Protocol


class SecretProviderPort(Protocol):
    """Port for reading string secrets/config values by key."""

    def get(self, key: str, default: str = "") -> str: ...


class SecretStorePort(Protocol):
    """Port for listing and persisting managed secret values."""

    def get(self, key: str, default: str = "") -> str: ...

    def has(self, key: str) -> bool: ...

    def items(self) -> Mapping[str, str]: ...

    def set(self, key: str, value: str) -> None: ...

    def delete(self, key: str) -> None: ...

    def save(self) -> None: ...


def require_secrets(provider: SecretProviderPort, keys: Sequence[str]) -> dict[str, str]:
    """Return required secret values or raise when any are missing."""
    values = {key: provider.get(key, "") for key in keys}
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required S3 environment variables: {', '.join(missing)}")
    return values
