from pathlib import Path

from src.adapters.secrets.env_secrets import EnvironmentSecretStore


def test_environment_secret_store_persists_and_deletes_keys(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    store = EnvironmentSecretStore(env_file=env_file.as_posix())

    store.set("S3_USERNAME", "alice")
    store.set("S3_SECRET_KEY", "super-secret")
    store.save()

    assert env_file.read_text() == 'S3_SECRET_KEY="super-secret"\nS3_USERNAME="alice"\n'

    reloaded = EnvironmentSecretStore(env_file=env_file.as_posix())
    assert reloaded.get("S3_USERNAME") == "alice"
    assert reloaded.has("S3_SECRET_KEY") is True

    reloaded.delete("S3_SECRET_KEY")
    reloaded.save()

    assert env_file.read_text() == 'S3_USERNAME="alice"\n'


def test_environment_secret_store_falls_back_to_process_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("S3_REGION", "us-east-1")
    store = EnvironmentSecretStore(env_file=(tmp_path / ".env").as_posix())

    assert store.get("S3_REGION") == "us-east-1"
    assert store.has("S3_REGION") is False
