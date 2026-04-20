from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from src.adapters import get_secret_provider_adapter, get_secret_store_adapter
from src.orchestration.secret_service import (
    MANAGED_S3_FIELDS,
    collect_secret_states,
    delete_secret_value,
    set_secret_value,
    validate_required_secret_values,
    validate_s3_connection,
)

ACTION_CHOICES = ["edit", "delete", "validate", "quit"]


def _render_secret_table(console: Console, provider_name: str, env_file: str) -> None:
    store = get_secret_store_adapter(provider_name, env_file=env_file)
    provider = store if provider_name == "env" else get_secret_provider_adapter(provider_name)
    table = Table(title=f"Secret Management ({provider_name})")
    table.add_column("Key", style="cyan")
    table.add_column("Label")
    table.add_column("Source")
    table.add_column("Value")

    for state in collect_secret_states(store, provider):
        table.add_row(state.field.key, state.field.label, state.source, state.masked_value)

    console.print(table)
    console.print(f"Backing file: {env_file}")


def _prompt_for_key(console: Console, action: str) -> str:
    del console
    return Prompt.ask(
        f"Select a key to {action}",
        choices=[field.key for field in MANAGED_S3_FIELDS],
    )


def _edit_secret(console: Console, provider_name: str, env_file: str) -> None:
    store = get_secret_store_adapter(provider_name, env_file=env_file)
    key = _prompt_for_key(console, "edit")
    field = next(field for field in MANAGED_S3_FIELDS if field.key == key)
    current_value = store.get(key, "")
    if current_value and not field.sensitive:
        value = Prompt.ask(
            f"{field.label}",
            default=current_value,
            password=field.sensitive,
            show_default=True,
        )
    else:
        value = Prompt.ask(f"{field.label}", password=field.sensitive)
    set_secret_value(store, key, value)
    console.print(f"Saved {key} to {env_file}")


def _delete_secret(console: Console, provider_name: str, env_file: str) -> None:
    store = get_secret_store_adapter(provider_name, env_file=env_file)
    key = _prompt_for_key(console, "delete")
    if not Confirm.ask(f"Delete {key} from {env_file}?", default=False):
        console.print("Delete cancelled")
        return
    delete_secret_value(store, key)
    console.print(f"Removed {key} from {env_file}")


def _validate(console: Console, provider_name: str, env_file: str, probe: bool) -> None:
    store = get_secret_store_adapter(provider_name, env_file=env_file)
    provider = store if provider_name == "env" else get_secret_provider_adapter(provider_name)
    validate_required_secret_values(provider)
    console.print("Required S3 secrets are present")
    if not probe:
        return
    validate_s3_connection(provider)
    console.print("S3 endpoint validation succeeded")


def _run(
    provider: Annotated[
        str,
        typer.Option(help="Secret provider/store to manage."),
    ] = "env",
    env_file: Annotated[
        str,
        typer.Option(help="Path to the .env file used by the env-backed secret store."),
    ] = ".env",
    probe: Annotated[
        bool,
        typer.Option(help="Probe the S3 endpoint during validation instead of only checking keys."),
    ] = False,
) -> None:
    console = Console()
    while True:
        _render_secret_table(console, provider, env_file)
        action = Prompt.ask("Action", choices=ACTION_CHOICES, default="edit")
        if action == "edit":
            _edit_secret(console, provider, env_file)
            continue
        if action == "delete":
            _delete_secret(console, provider, env_file)
            continue
        if action == "validate":
            _validate(console, provider, env_file, probe)
            continue
        break


def main() -> None:
    typer.run(_run)


if __name__ == "__main__":
    main()
