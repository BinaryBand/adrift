"""CLI helpers and command entrypoints for adrift."""

from collections.abc import Callable
from typing import Annotated

import dotenv
import typer

from adrift.models import PodcastConfig

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


def load_podcast_configs(
    include: list[str],
    skip_schedule_filter: bool,
    tags: list[str],
) -> list[PodcastConfig]:
    from adrift.app_common import filter_podcasts_by_tags, load_podcasts_config

    configs = load_podcasts_config(
        include=include,
        skip_schedule_filter=skip_schedule_filter,
    )
    return filter_podcasts_by_tags(configs, tags)


def bootstrap_run_configs(
    include: list[str] | None,
    tags: list[str] | None,
    skip_schedule_filter: bool,
    output_dir: str | None = None,
) -> tuple[list[PodcastConfig], str]:
    dotenv.load_dotenv()
    normalized_include, normalized_tags, normalized_output_dir = normalize_cli_inputs(
        include,
        tags,
        output_dir,
    )
    configs = load_podcast_configs(normalized_include, skip_schedule_filter, normalized_tags)
    return configs, normalized_output_dir


def make_main(app: typer.Typer) -> Callable[[], None]:
    def _main() -> None:
        app(standalone_mode=False)

    return _main


def build_cli(run_handler: Callable[..., None]) -> tuple[typer.Typer, Callable[[], None]]:
    app = typer.Typer(add_completion=False)
    app.callback(invoke_without_command=True)(run_handler)
    return app, make_main(app)
