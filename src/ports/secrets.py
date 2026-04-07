from typing import Protocol, Sequence


class SecretProviderPort(Protocol):
    """Port for reading string secrets/config values by key."""

    def get(self, key: str, default: str = "") -> str: ...


def require_secrets(provider: SecretProviderPort, keys: Sequence[str]) -> dict[str, str]:
    """Return required secret values or raise when any are missing."""
    values = {key: provider.get(key, "") for key in keys}
    missing = [key for key, value in values.items() if not value]
    if missing:
        missing_list = ", ".join(missing)
        raise RuntimeError(f"Missing required S3 environment variables: {missing_list}")
    return values
