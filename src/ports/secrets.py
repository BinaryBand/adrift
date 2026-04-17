from typing import Protocol


class SecretProviderPort(Protocol):
    """Port for reading string secrets/config values by key."""

    def get(self, key: str, default: str = "") -> str: ...
