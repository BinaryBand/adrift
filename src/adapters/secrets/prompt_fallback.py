from __future__ import annotations

from collections.abc import Callable

from rich.prompt import Prompt

from src.orchestration.secret_service import describe_managed_secret
from src.ports import SecretProviderPort

PromptCallback = Callable[[str, str, bool], str]


def prompt_for_secret_value(key: str, label: str, sensitive: bool) -> str:
    return Prompt.ask(label, password=sensitive)


class PromptFallbackProvider(SecretProviderPort):
    """Prompt for missing values after consulting an underlying provider."""

    def __init__(
        self,
        provider: SecretProviderPort,
        *,
        prompt_callback: PromptCallback = prompt_for_secret_value,
    ):
        self._provider = provider
        self._prompt_callback = prompt_callback
        self._cache: dict[str, str] = {}

    def get(self, key: str, default: str = "") -> str:
        cached_value = self._cache.get(key)
        if cached_value:
            return cached_value

        value = self._provider.get(key, "")
        if value:
            return value

        prompted_value = self._prompt_for_missing_value(key, default)
        if not prompted_value:
            return default

        self._cache[key] = prompted_value
        return prompted_value

    def _prompt_for_missing_value(self, key: str, default: str) -> str:
        label, sensitive = _describe_prompt_target(key)

        try:
            return self._prompt_callback(key, label, sensitive)
        except (EOFError, KeyboardInterrupt):
            return default


def _describe_prompt_target(key: str) -> tuple[str, bool]:
    field = describe_managed_secret(key)
    if field is None:
        return key, False
    return field.label, field.sensitive
