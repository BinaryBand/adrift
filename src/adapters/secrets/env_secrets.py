import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from src.ports import SecretProviderPort, SecretStorePort


class EnvironmentSecretProvider(SecretProviderPort):
    """Default adapter that reads secrets from process environment variables."""

    def __init__(self, load_dotenv_file: bool = True):
        if load_dotenv_file:
            load_dotenv(find_dotenv())

    def get(self, key: str, default: str = "") -> str:
        return os.getenv(key, default)


class EnvironmentSecretStore(SecretStorePort):
    """Writable `.env` store used by the secret-management TUI."""

    def __init__(self, env_file: str = ".env"):
        self.env_path = Path(env_file)
        self._values = _load_env_values(self.env_path)

    def get(self, key: str, default: str = "") -> str:
        if key in self._values:
            return self._values[key]
        return os.getenv(key, default)

    def has(self, key: str) -> bool:
        return key in self._values

    def items(self) -> dict[str, str]:
        return dict(self._values)

    def set(self, key: str, value: str) -> None:
        self._values[key] = value

    def delete(self, key: str) -> None:
        self._values.pop(key, None)

    def save(self) -> None:
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        rendered = "\n".join(
            _render_env_line(key, value) for key, value in sorted(self._values.items())
        )
        if rendered:
            rendered += "\n"
        self.env_path.write_text(rendered, encoding="utf-8")


def _load_env_values(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        key, value = _parse_env_line(raw_line)
        if key is not None:
            values[key] = value
    return values


def _parse_env_line(raw_line: str) -> tuple[str | None, str]:
    line = raw_line.strip()
    if _should_skip_env_line(line):
        return None, ""
    key, raw_value = line.split("=", 1)
    return key.strip(), _decode_env_value(raw_value.strip())


def _should_skip_env_line(line: str) -> bool:
    return not line or line.startswith("#") or "=" not in line


def _decode_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1]
    return value.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")


def _render_env_line(key: str, value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'{key}="{escaped}"'
