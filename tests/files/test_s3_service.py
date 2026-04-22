from __future__ import annotations

from typing import Any

from src.files.s3 import S3Service


class _FakeProvider:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)


class _FakeSession:
    def __init__(self) -> None:
        self.last_kwargs: dict[str, Any] | None = None

    def client(self, service_name: str, **kwargs: Any) -> dict[str, Any]:
        self.last_kwargs = {"service_name": service_name, **kwargs}
        return self.last_kwargs


def test_build_client_uses_secret_values_not_key_names() -> None:
    values = {
        "S3_USERNAME": "alice",
        "S3_SECRET_KEY": "secret-123",
        "S3_ENDPOINT": "https://s3.example.com",
        "S3_REGION": "eu-north-1",
    }
    provider = _FakeProvider(values)
    session = _FakeSession()

    service = S3Service(
        provider,
        session_factory=lambda: session,
    )

    client = service.build_client()

    assert isinstance(client, dict)
    assert client["service_name"] == "s3"
    assert client["aws_access_key_id"] == values["S3_USERNAME"]
    assert client["aws_secret_access_key"] == values["S3_SECRET_KEY"]
    assert client["endpoint_url"] == values["S3_ENDPOINT"]
    assert client["region_name"] == values["S3_REGION"]


def test_get_effective_endpoint_uses_secret_value() -> None:
    values = {
        "S3_USERNAME": "alice",
        "S3_SECRET_KEY": "secret-123",
        "S3_ENDPOINT": "https://s3.example.com",
        "S3_REGION": "eu-north-1",
        "LOCAL_S3_ENDPOINT": "",
    }
    provider = _FakeProvider(values)
    service = S3Service(provider, session_factory=lambda: _FakeSession())

    assert service.get_effective_endpoint() == "https://s3.example.com"
