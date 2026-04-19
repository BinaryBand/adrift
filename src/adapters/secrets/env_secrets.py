import os

from dotenv import find_dotenv, load_dotenv

from src.ports.secrets import SecretProviderPort


class EnvironmentSecretProvider(SecretProviderPort):
    """Default adapter that reads secrets from process environment variables."""

    def __init__(self, load_dotenv_file: bool = True):
        if load_dotenv_file:
            load_dotenv(find_dotenv())

    def get(self, key: str, default: str = "") -> str:
        return os.getenv(key, default)
