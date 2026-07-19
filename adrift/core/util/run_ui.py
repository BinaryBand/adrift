"""Progress-bar run UIs (tqdm and rich) for the merge/download pipelines."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from contextlib import AbstractContextManager
from types import TracebackType

from rich.progress import Progress
from tqdm import tqdm
from typing_extensions import override

from adrift.core.util.progress import Callback
from adrift.core.util.terminal import Level, format_terminal_message, using_terminal_emitter

_PROGRESS_META_WIDTH = 38


def _render_stage_description(name: str, stage: str | None) -> str:
    if not stage:
        return name
    return f"{name} [{stage}]"


def _fit_progress_description(description: str, console_width: int) -> str:
    max_width = max(console_width - _PROGRESS_META_WIDTH, 24)
    if len(description) <= max_width:
        return description
    return f"{description[: max_width - 3].rstrip()}..."


class BaseRunUI(AbstractContextManager["BaseRunUI"]):
    """Base run UI: tracks the current podcast/stage/operation labels."""

    def __init__(self, total: int, label: str) -> None:
        """Initialize the UI for ``total`` items under ``label``."""
        self.total = total
        self.label = label
        self.current_name = label
        self.current_stage: str | None = None
        self.current_operation: str | None = None

    def stage_callback(self, stage: str) -> None:
        """Callback adapter forwarding a stage change to ``set_stage``."""
        self.set_stage(stage)

    def progress_callback(self, current: int, total: int | None) -> None:
        """Callback adapter forwarding progress to ``update_progress``."""
        self.update_progress(current, total)

    def operation_callback(self, current: int, total: int | None) -> None:
        """Callback adapter forwarding operation progress."""
        self.update_operation_progress(current, total)

    def output_context(self) -> AbstractContextManager[None]:
        """Return a context manager routing terminal output through ``emit``."""
        return using_terminal_emitter(self.emit)

    def set_podcast(self, name: str) -> None:
        """Set the current podcast name and reset the stage."""
        self.current_name = name
        self.current_stage = None

    def set_stage(self, stage: str) -> None:
        """Set the current pipeline stage label."""
        self.current_stage = stage

    def set_operation(self, operation: str) -> None:
        """Set the current fine-grained operation label."""
        self.current_operation = operation

    def clear_operation(self) -> None:
        """Clear the current operation label."""
        self.current_operation = None

    def update_progress(self, current: int, total: int | None) -> None:
        """Update overall progress (no-op in the base UI)."""
        del current, total

    def update_operation_progress(self, current: int, total: int | None) -> None:
        """Update operation progress (no-op in the base UI)."""
        del current, total

    def advance(self) -> None:
        """Advance the overall progress by one item."""
        raise NotImplementedError

    def emit(self, level: Level, message: str) -> None:
        """Emit ``message`` at ``level`` to the UI's output channel."""
        raise NotImplementedError

    def close(self) -> None:
        """Release any UI resources."""
        return

    @override
    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        del exc
        self.close()


class TqdmRunUI(BaseRunUI):
    """Run UI backed by a tqdm progress bar (fallback when rich is absent)."""

    def __init__(self, total: int, label: str) -> None:
        """Initialize a tqdm bar for ``total`` items under ``label``."""
        super().__init__(total, label)
        self._bar = tqdm(total=total, desc=label, unit="podcast", file=sys.stderr)

    @override
    def set_podcast(self, name: str) -> None:
        super().set_podcast(name)
        self._bar.set_description(name)
        self._bar.set_postfix_str("")

    @override
    def set_stage(self, stage: str) -> None:
        super().set_stage(stage)
        self._bar.set_postfix_str(stage)

    @override
    def set_operation(self, operation: str) -> None:
        super().set_operation(operation)
        self._bar.set_postfix_str(f"{self.current_stage or ''} {operation}".strip())

    @override
    def clear_operation(self) -> None:
        super().clear_operation()
        self._bar.set_postfix_str(self.current_stage or "")

    @override
    def emit(self, level: Level, message: str) -> None:
        self._bar.write(format_terminal_message(level, message))

    @override
    def advance(self) -> None:
        self._bar.update(1)

    @override
    def close(self) -> None:
        self._bar.close()


class RichRunUI(BaseRunUI):
    """Run UI backed by a rich multi-task progress display."""

    def __init__(self, total: int, label: str) -> None:
        """Initialize the rich progress tasks for ``total`` items."""
        super().__init__(total, label)
        self._progress = _build_rich_progress()
        self._progress.start()
        self._overall_task = self._progress.add_task(self._fit(label), total=total)
        self._detail_task = self._progress.add_task("Idle", total=None, visible=False)
        self._operation_task = self._progress.add_task("Idle", total=None, visible=False)

    def _fit(self, description: str) -> str:
        return _fit_progress_description(description, self._progress.console.width)

    @override
    def set_podcast(self, name: str) -> None:
        super().set_podcast(name)
        self._progress.update(
            self._detail_task,
            visible=True,
            total=None,
            completed=0,
            description=self._fit(name),
        )
        self._progress.update(self._operation_task, visible=False, total=None, completed=0)

    @override
    def set_stage(self, stage: str) -> None:
        super().set_stage(stage)
        self._progress.update(
            self._detail_task,
            description=self._fit(f"{self.current_name} {stage}"),
        )

    @override
    def update_progress(self, current: int, total: int | None) -> None:
        description = _render_stage_description(self.current_name, self.current_stage)
        self._progress.update(
            self._detail_task,
            description=self._fit(description),
            total=total,
            completed=current,
            visible=True,
        )

    @override
    def set_operation(self, operation: str) -> None:
        super().set_operation(operation)
        self._progress.update(
            self._operation_task,
            description=self._operation_description(),
            total=None,
            completed=0,
            visible=True,
        )

    @override
    def clear_operation(self) -> None:
        super().clear_operation()
        self._progress.update(self._operation_task, visible=False, total=None, completed=0)

    @override
    def update_operation_progress(self, current: int, total: int | None) -> None:
        self._progress.update(
            self._operation_task,
            description=self._operation_description(),
            total=total,
            completed=current,
            visible=True,
        )

    def _operation_description(self) -> str:
        description = self.current_name
        if self.current_stage:
            description = f"{description} {self.current_stage}"
        if self.current_operation:
            description = f"{description} {self.current_operation}"
        return self._fit(description)

    @override
    def emit(self, level: Level, message: str) -> None:
        style = {
            "info": "white",
            "warning": "yellow",
            "error": "bold red",
        }[level]
        prefix = {
            "info": "",
            "warning": "WARNING: ",
            "error": "ERROR: ",
        }[level]
        self._progress.console.print(f"[{style}]{prefix}{message}[/{style}]")

    @override
    def advance(self) -> None:
        self._progress.advance(self._overall_task)
        self._progress.update(self._detail_task, total=None, completed=0)

    @override
    def close(self) -> None:
        self._progress.stop()


def create_run_ui(total: int, label: str) -> BaseRunUI:
    """Return a rich run UI when available, else a tqdm fallback."""
    if not _rich_is_available():
        return TqdmRunUI(total, label)
    return RichRunUI(total, label)


def _rich_is_available() -> bool:
    return importlib.util.find_spec("rich") is not None


def _build_rich_progress() -> Progress:
    # rich is an optional dependency; import lazily so the module loads without it.
    from rich.console import Console  # noqa: PLC0415
    from rich.progress import (  # noqa: PLC0415
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
    )
    from rich.table import Column  # noqa: PLC0415

    return Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("{task.description}", table_column=Column(ratio=3, min_width=24)),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=Console(stderr=True),
        transient=False,
        expand=True,
    )


def build_merge_callbacks(ui: BaseRunUI) -> tuple[Callable[[str], None], Callback]:
    """Return the (stage, progress) callback pair bound to ``ui``."""
    return ui.stage_callback, ui.progress_callback
