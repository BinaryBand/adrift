from pathlib import Path

import pytest

from src.adapters import get_secret_store_adapter
from src.adapters.secrets.docker_secrets import DockerSecretProvider
from src.ports import SecretStorePort


def test_docker_secret_provider_reads_file(tmp_path: Path):
    # Create a fake secret file
    secret_name = "MY_SECRET"
    secret_value = "supersecret"
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    secret_file = secrets_dir / secret_name
    secret_file.write_text(secret_value)

    provider = DockerSecretProvider(secrets_dir=str(secrets_dir))
    assert provider.get(secret_name) == secret_value
    # Should return default if not found
    assert provider.get("MISSING", default="fallback") == "fallback"


def test_docker_secret_provider_fallback_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    secret_name = "ENV_SECRET"
    secret_value = "envvalue"
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    # No file for ENV_SECRET
    monkeypatch.setenv(secret_name, secret_value)
    provider = DockerSecretProvider(secrets_dir=str(secrets_dir))
    assert provider.get(secret_name) == secret_value


def test_docker_secret_store_is_read_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secret_name = "S3_REGION"
    secret_value = "us-east-1"
    monkeypatch.setenv(secret_name, secret_value)
    monkeypatch.setenv("ADRIFT_SECRETS_PROVIDER", "docker")

    store = get_secret_store_adapter()

    assert store.get(secret_name) == secret_value
    assert store.has(secret_name) is True
    assert store.items()[secret_name] == secret_value
    assert isinstance(store, SecretStorePort) is False
