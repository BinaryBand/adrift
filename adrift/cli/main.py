"""Top-level `adrift` CLI entrypoint."""

from typing import Annotated

import click
import typer

from adrift.cli.cleanup import app as cleanup_app
from adrift.cli.download import app as download_app
from adrift.cli.merge import app as merge_app
from adrift.cli.schema import app as schema_app

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="adrift CLI with grouped subcommands.",
)
app.add_typer(cleanup_app, name="cleanup")
app.add_typer(download_app, name="download")
app.add_typer(merge_app, name="merge")
app.add_typer(schema_app, name="schema")


@app.command("help")
def help_command(
    ctx: typer.Context,
    command: Annotated[
        str | None,
        typer.Argument(help="Subcommand name to show help for."),
    ] = None,
) -> None:
    """Show help for adrift or a subcommand."""
    root_ctx = ctx.parent or ctx
    root_command = root_ctx.command

    if command is None:
        typer.echo(root_ctx.get_help())
        return

    if not isinstance(root_command, click.Group):
        raise typer.BadParameter("This command does not support subcommands.")

    target = root_command.get_command(root_ctx, command)
    if target is None:
        raise typer.BadParameter(f"Unknown command '{command}'.", param_hint="command")

    target_ctx = click.Context(
        target,
        info_name=command,
        parent=root_ctx,
    )
    typer.echo(target.get_help(target_ctx))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
