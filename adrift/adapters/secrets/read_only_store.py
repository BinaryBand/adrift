from __future__ import annotations

from collections.abc import Iterable, Mapping

from src.ports import ReadOnlySecretStorePort, SecretProviderPort


class ReadOnlySecretStore(ReadOnlySecretStorePort):
    """Read-only inspection wrapper for non-writable secret backends."""

    def __init__(self, provider: SecretProviderPort, *, known_keys: Iterable[str] = ()):
        self._provider = provider
        self._known_keys = tuple(known_keys)

    def get(self, key: str, default: str = "") -> str:
        return self._provider.get(key, default)

    def has(self, key: str) -> bool:
        return bool(self.get(key, ""))

    def items(self) -> Mapping[str, str]:
        return {key: value for key in self._known_keys if (value := self.get(key, ""))}
