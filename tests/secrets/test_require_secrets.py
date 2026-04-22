import pytest

from src.ports import require_secrets


class _FakeProvider:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)


def test_require_secrets_returns_values_when_all_present() -> None:
    provider = _FakeProvider(
        {
            "S3_USERNAME": "alice",
            "S3_SECRET_KEY": "secret",
            "S3_ENDPOINT": "https://s3.example.com",
            "S3_REGION": "us-east-1",
        }
    )

    values = require_secrets(
        provider,
        ("S3_USERNAME", "S3_SECRET_KEY", "S3_ENDPOINT", "S3_REGION"),
    )

    assert values["S3_REGION"] == "us-east-1"


def test_require_secrets_rejects_literal_key_placeholders() -> None:
    provider = _FakeProvider(
        {
            "S3_USERNAME": "alice",
            "S3_SECRET_KEY": "secret",
            "S3_ENDPOINT": "https://s3.example.com",
            "S3_REGION": "S3_REGION",
        }
    )

    with pytest.raises(RuntimeError) as exc:
        require_secrets(
            provider,
            ("S3_USERNAME", "S3_SECRET_KEY", "S3_ENDPOINT", "S3_REGION"),
        )
    assert "S3_REGION" in str(exc.value)


def test_require_secrets_rejects_shell_style_placeholders() -> None:
    provider = _FakeProvider(
        {
            "S3_USERNAME": "alice",
            "S3_SECRET_KEY": "secret",
            "S3_ENDPOINT": "https://s3.example.com",
            "S3_REGION": "${S3_REGION}",
        }
    )

    with pytest.raises(RuntimeError) as exc:
        require_secrets(
            provider,
            ("S3_USERNAME", "S3_SECRET_KEY", "S3_ENDPOINT", "S3_REGION"),
        )
    assert "S3_REGION" in str(exc.value)
