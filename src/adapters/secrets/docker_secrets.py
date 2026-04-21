import os

from src.ports import SecretProviderPort


class DockerSecretProvider(SecretProviderPort):
    """
    Adapter that reads secrets from Docker secrets (mounted files in /run/secrets)
    or environment.
    """

    def __init__(self, secrets_dir: str = "/run/secrets"):
        self.secrets_dir = secrets_dir

    def get(self, key: str, default: str = "") -> str:
        # Try Docker secrets file first
        secret_path = os.path.join(self.secrets_dir, key)
        if os.path.isfile(secret_path):
            with open(secret_path, "r") as f:
                return f.read().strip()
        # Fallback to environment variable
        return os.getenv(key, default)
