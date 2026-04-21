from unittest.mock import Mock

from src.adapters.secrets.prompt_fallback import PromptFallbackProvider


def test_prompt_fallback_uses_base_provider_value() -> None:
    provider = Mock()
    provider.get.return_value = "alice"
    prompt_callback = Mock(return_value="prompted")

    wrapped = PromptFallbackProvider(provider, prompt_callback=prompt_callback)

    assert wrapped.get("S3_USERNAME") == "alice"
    prompt_callback.assert_not_called()


def test_prompt_fallback_prompts_for_missing_value() -> None:
    provider = Mock()
    provider.get.return_value = ""
    prompt_callback = Mock(return_value="secret-123")

    wrapped = PromptFallbackProvider(provider, prompt_callback=prompt_callback)

    assert wrapped.get("S3_SECRET_KEY") == "secret-123"
    prompt_callback.assert_called_once_with("S3_SECRET_KEY", "S3 secret key", True)


def test_prompt_fallback_returns_default_when_prompt_is_cancelled() -> None:
    provider = Mock()
    provider.get.return_value = ""
    prompt_callback = Mock(side_effect=KeyboardInterrupt())

    wrapped = PromptFallbackProvider(provider, prompt_callback=prompt_callback)

    assert wrapped.get("S3_REGION", default="us-east-1") == "us-east-1"
