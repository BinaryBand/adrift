"""CLI helpers and command entrypoints for adrift."""

from collections.abc import Callable
from typing import Annotated

import typer

from adrift.services.app_common import bootstrap_run_configs as bootstrap_run_configs
from adrift.services.app_common import load_podcast_configs as load_podcast_configs

DF_TARGETS = ["config/*.toml"]
DEFAULT_OUTPUT_DIR = "downloads"

IncludeConfigsOption = Annotated[list[str] | None, typer.Option(help="Config files to include")]
SkipScheduleFilterOption = Annotated[
    bool,
    typer.Option(help="Include podcast configs even when their schedule does not match today."),
]
TagsOption = Annotated[
    list[str] | None,
    typer.Option(help="Tag(s) or podcast names to limit scope"),
]


def normalize_cli_inputs(
    include: list[str] | None,
    tags: list[str] | None,
    output_dir: str | None = None,
) -> tuple[list[str], list[str], str]:
    """Normalize CLI inputs for adrift commands."""
    return (include or DF_TARGETS, tags or [], output_dir or DEFAULT_OUTPUT_DIR)


def make_main(app: typer.Typer) -> Callable[[], None]:
    def _main() -> None:
        app(standalone_mode=False)

    return _main


def build_cli(run_handler: Callable[..., None]) -> tuple[typer.Typer, Callable[[], None]]:
    app = typer.Typer(add_completion=False)
    app.callback(invoke_without_command=True)(run_handler)
    return app, make_main(app)
