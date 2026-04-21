from __future__ import annotations

from typing import Annotated, Any

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from src.adapters import get_secret_provider_adapter, get_secret_store_adapter
from src.orchestration.secret_service import (
    MANAGED_S3_FIELDS,
    collect_secret_states,
    delete_secret_value,
    is_writable_secret_store,
    set_secret_value,
    validate_required_secret_values,
    validate_s3_connection,
)
from src.ports import SecretStorePort

READ_ONLY_ACTION_CHOICES = ["validate", "quit"]
WRITABLE_ACTION_CHOICES = ["edit", "delete", "validate", "quit"]


def _resolve_provider(provider_name: str):
    return get_secret_provider_adapter(provider_name, enable_prompt_fallback=False)


def _resolve_store(provider_name: str, env_file: str):
    return get_secret_store_adapter(provider_name, env_file=env_file)


def _management_provider(provider_name: str, store: object):
    if provider_name == "env" and isinstance(store, SecretStorePort):
        return store
    return _resolve_provider(provider_name)


def _action_choices(store: Any) -> list[str]:
    if is_writable_secret_store(store):
        return WRITABLE_ACTION_CHOICES
    return READ_ONLY_ACTION_CHOICES


def _render_secret_table(console: Console, provider_name: str, env_file: str) -> None:
    store = _resolve_store(provider_name, env_file)
    provider = _management_provider(provider_name, store)
    table = Table(title=f"Secret Management ({provider_name})")
    table.add_column("Key", style="cyan")
    table.add_column("Label")
    table.add_column("Source")
    table.add_column("Value")

    for state in collect_secret_states(store, provider, provider_name=provider_name):
        table.add_row(state.field.key, state.field.label, state.source, state.masked_value)

    console.print(table)
    if is_writable_secret_store(store):
        console.print(f"Backing file: {env_file}")
    else:
        console.print(f"Provider '{provider_name}' is inspect-only in this runbook session")


def _prompt_for_key(console: Console, action: str) -> str:
    del console
    return Prompt.ask(
        f"Select a key to {action}",
        choices=[field.key for field in MANAGED_S3_FIELDS],
    )


def _edit_secret(console: Console, provider_name: str, env_file: str) -> None:
    store = _resolve_store(provider_name, env_file)
    if not is_writable_secret_store(store):
        console.print(f"Provider '{provider_name}' is read-only; edit is unavailable")
        return
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
    store = _resolve_store(provider_name, env_file)
    if not is_writable_secret_store(store):
        console.print(f"Provider '{provider_name}' is read-only; delete is unavailable")
        return
    key = _prompt_for_key(console, "delete")
    if not Confirm.ask(f"Delete {key} from {env_file}?", default=False):
        console.print("Delete cancelled")
        return
    delete_secret_value(store, key)
    console.print(f"Removed {key} from {env_file}")


def _validate(console: Console, provider_name: str, env_file: str, probe: bool) -> None:
    store = _resolve_store(provider_name, env_file)
    provider = _management_provider(provider_name, store)
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
        store = _resolve_store(provider, env_file)
        _render_secret_table(console, provider, env_file)
        action_choices = _action_choices(store)
        default_action = "edit" if "edit" in action_choices else "validate"
        action = Prompt.ask("Action", choices=action_choices, default=default_action)
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
