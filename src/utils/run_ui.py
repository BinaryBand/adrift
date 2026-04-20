from __future__ import annotations

import importlib.util
import sys
from contextlib import AbstractContextManager
from typing import Any, Callable

from tqdm import tqdm

from src.utils.progress import Callback
from src.utils.terminal import Level, using_terminal_emitter

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
    def __init__(self, total: int, label: str) -> None:
        self.total = total
        self.label = label
        self.current_name = label
        self.current_stage: str | None = None
        self.current_operation: str | None = None

    def stage_callback(self, stage: str) -> None:
        self.set_stage(stage)

    def progress_callback(self, current: int, total: int | None) -> None:
        self.update_progress(current, total)

    def operation_callback(self, current: int, total: int | None) -> None:
        self.update_operation_progress(current, total)

    def output_context(self):
        return using_terminal_emitter(self.emit)

    def set_podcast(self, name: str) -> None:
        self.current_name = name
        self.current_stage = None

    def set_stage(self, stage: str) -> None:
        self.current_stage = stage

    def set_operation(self, operation: str) -> None:
        self.current_operation = operation

    def clear_operation(self) -> None:
        self.current_operation = None

    def update_progress(self, current: int, total: int | None) -> None:
        del current, total

    def update_operation_progress(self, current: int, total: int | None) -> None:
        del current, total

    def advance(self) -> None:
        raise NotImplementedError

    def emit(self, level: Level, message: str) -> None:
        raise NotImplementedError

    def close(self) -> None:
        return

    def __exit__(self, _exc_type: Any, exc: Any, _tb: Any) -> None:
        del exc
        self.close()
        return None


class TqdmRunUI(BaseRunUI):
    def __init__(self, total: int, label: str) -> None:
        super().__init__(total, label)
        self._bar = tqdm(total=total, desc=label, unit="podcast", file=sys.stderr)

    def set_podcast(self, name: str) -> None:
        super().set_podcast(name)
        self._bar.set_description(name)
        self._bar.set_postfix_str("")

    def set_stage(self, stage: str) -> None:
        super().set_stage(stage)
        self._bar.set_postfix_str(stage)

    def set_operation(self, operation: str) -> None:
        super().set_operation(operation)
        self._bar.set_postfix_str(f"{self.current_stage or ''} {operation}".strip())

    def clear_operation(self) -> None:
        super().clear_operation()
        self._bar.set_postfix_str(self.current_stage or "")

    def emit(self, level: Level, message: str) -> None:
        prefix = {
            "info": "",
            "warning": "WARNING: ",
            "error": "ERROR: ",
        }[level]
        self._bar.write(f"{prefix}{message}")

    def advance(self) -> None:
        self._bar.update(1)

    def close(self) -> None:
        self._bar.close()


class RichRunUI(BaseRunUI):
    def __init__(self, total: int, label: str) -> None:
        super().__init__(total, label)
        self._progress = _build_rich_progress()
        self._progress.start()
        self._overall_task = self._progress.add_task(self._fit(label), total=total)
        self._detail_task = self._progress.add_task("Idle", total=None, visible=False)
        self._operation_task = self._progress.add_task("Idle", total=None, visible=False)

    def _fit(self, description: str) -> str:
        return _fit_progress_description(description, self._progress.console.width)

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

    def set_stage(self, stage: str) -> None:
        super().set_stage(stage)
        self._progress.update(
            self._detail_task,
            description=self._fit(f"{self.current_name} {stage}"),
        )

    def update_progress(self, current: int, total: int | None) -> None:
        description = _render_stage_description(self.current_name, self.current_stage)
        self._progress.update(
            self._detail_task,
            description=self._fit(description),
            total=total,
            completed=current,
            visible=True,
        )

    def set_operation(self, operation: str) -> None:
        super().set_operation(operation)
        self._progress.update(
            self._operation_task,
            description=self._operation_description(),
            total=None,
            completed=0,
            visible=True,
        )

    def clear_operation(self) -> None:
        super().clear_operation()
        self._progress.update(self._operation_task, visible=False, total=None, completed=0)

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

    def advance(self) -> None:
        self._progress.advance(self._overall_task)
        self._progress.update(self._detail_task, total=None, completed=0)

    def close(self) -> None:
        self._progress.stop()


def create_run_ui(total: int, label: str) -> BaseRunUI:
    if not _rich_is_available():
        return TqdmRunUI(total, label)
    return RichRunUI(total, label)


def _rich_is_available() -> bool:
    return importlib.util.find_spec("rich") is not None


def _build_rich_progress():
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
    )
    from rich.table import Column

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
    return ui.stage_callback, ui.progress_callback
