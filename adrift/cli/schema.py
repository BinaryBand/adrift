"""Schema tooling CLI for config authoring and validation."""

from typing import Annotated

import typer

from adrift.services.schema_service import compile_config_schema

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Schema tooling commands.")


@app.command("compile")
def compile_command(
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Output JSON schema path."),
    ] = "adrift/models/podcasts.schema.json",
) -> None:
    """Compile JSON Schema for config/*.toml and write it to disk."""
    out = compile_config_schema(output)
    typer.echo(f"Wrote schema: {out}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
