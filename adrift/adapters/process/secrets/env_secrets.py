"""Environment variable secrets provider adapter."""

import os

from dotenv import find_dotenv, load_dotenv
from typing_extensions import override

from adrift.core.ports import SecretProviderPort


class EnvironmentSecretProvider(SecretProviderPort):
    """Default adapter that reads secrets from process environment variables."""

    source_name = "env"

    def __init__(self, load_dotenv_file: bool = True) -> None:  # noqa: FBT001, FBT002
        """Initialize the secret provider, optionally loading dotenv."""
        if load_dotenv_file:
            load_dotenv(find_dotenv())

    @override
    def get(self, key: str, default: str = "") -> str:
        return os.getenv(key, default)
