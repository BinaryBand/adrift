"""Service helpers for compiling configuration schemas."""

from pathlib import Path

from adrift.models import compile_podcast_toml_schema


def compile_config_schema(output_path: str | Path = "adrift/models/podcasts.schema.json") -> Path:
    """Compile JSON schema used for validating config TOML files."""
    return compile_podcast_toml_schema(output_path)
