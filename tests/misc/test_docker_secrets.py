from src.adapters.secrets.docker_secrets import DockerSecretProvider


def test_docker_secret_provider_reads_file(tmp_path):
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


def test_docker_secret_provider_fallback_env(monkeypatch, tmp_path):
    secret_name = "ENV_SECRET"
    secret_value = "envvalue"
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    # No file for ENV_SECRET
    monkeypatch.setenv(secret_name, secret_value)
    provider = DockerSecretProvider(secrets_dir=str(secrets_dir))
    assert provider.get(secret_name) == secret_value
