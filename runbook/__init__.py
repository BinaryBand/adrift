"""Runbook commands and project maintenance tools."""

DF_TARGETS = ["config/*.toml"]
DEFAULT_OUTPUT_DIR = "downloads"


def normalize_cli_inputs(
    include: list[str] | None,
    tags: list[str] | None,
    output_dir: str | None = None,
) -> tuple[list[str], list[str], str]:
    """Normalize CLI inputs for runbook commands.

    Returns:
        (include, tags, output_dir) normalized tuple. output_dir defaults to DEFAULT_OUTPUT_DIR.
    """
    return (include or DF_TARGETS, tags or [], output_dir or DEFAULT_OUTPUT_DIR)
