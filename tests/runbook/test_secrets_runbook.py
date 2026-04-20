from pathlib import Path
from unittest.mock import patch

from runbook import secrets as secrets_mod


def test_runbook_edits_and_deletes_secrets(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    responses = iter(
        [
            "edit",
            "S3_USERNAME",
            "alice",
            "edit",
            "S3_SECRET_KEY",
            "secret-123",
            "delete",
            "S3_USERNAME",
            "quit",
        ]
    )
    confirms = iter([True])

    monkeypatch.chdir(tmp_path)

    def _ask(*args, **kwargs):
        del args, kwargs
        return next(responses)

    def _confirm(*args, **kwargs):
        del args, kwargs
        return next(confirms)

    with (
        patch("runbook.secrets.Prompt.ask", side_effect=_ask),
        patch("runbook.secrets.Confirm.ask", side_effect=_confirm),
    ):
        secrets_mod._run(provider="env", env_file=env_file.as_posix(), probe=False)

    assert env_file.read_text() == 'S3_SECRET_KEY="secret-123"\n'


def test_runbook_validation_uses_secret_service(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        'S3_ENDPOINT="https://s3.example.com"\n'
        'S3_REGION="us-east-1"\n'
        'S3_SECRET_KEY="secret-123"\n'
        'S3_USERNAME="alice"\n',
        encoding="utf-8",
    )

    with (
        patch("runbook.secrets.validate_required_secret_values") as mock_validate_required,
        patch("runbook.secrets.validate_s3_connection") as mock_validate_connection,
    ):
        secrets_mod._validate(secrets_mod.Console(), "env", env_file.as_posix(), probe=True)

    assert mock_validate_required.called is True
    assert mock_validate_connection.called is True


def test_runbook_read_only_provider_only_offers_validate_and_quit(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    env_file = tmp_path / ".env"
    monkeypatch.setenv("S3_REGION", "us-east-1")
    monkeypatch.setenv("S3_USERNAME", "alice")
    monkeypatch.setenv("S3_SECRET_KEY", "secret-123")
    monkeypatch.setenv("S3_ENDPOINT", "https://s3.example.com")

    responses = iter(["validate", "quit"])

    def _ask(*args, **kwargs):
        del args, kwargs
        return next(responses)

    with patch("runbook.secrets.Prompt.ask", side_effect=_ask):
        secrets_mod._run(provider="docker", env_file=env_file.as_posix(), probe=False)

    output = capsys.readouterr().out
    assert "inspect-only" in output
    assert "Required S3 secrets are present" in output
