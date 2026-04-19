from __future__ import annotations

import importlib.util
import sys
from contextlib import AbstractContextManager
from typing import Any, Callable

from tqdm import tqdm

from src.utils.progress import Callback
from src.utils.terminal import Level, using_terminal_emitter


def _render_stage_description(name: str, stage: str | None) -> str:
    if not stage:
        return name
    return f"{name} [{stage}]"


class BaseRunUI(AbstractContextManager["BaseRunUI"]):
    def __init__(self, total: int, label: str) -> None:
        self.total = total
        self.label = label
        self.current_name = label
        self.current_stage: str | None = None

    def stage_callback(self, stage: str) -> None:
        self.set_stage(stage)

    def progress_callback(self, current: int, total: int | None) -> None:
        self.update_progress(current, total)

    def output_context(self):
        return using_terminal_emitter(self.emit)

    def set_podcast(self, name: str) -> None:
        self.current_name = name
        self.current_stage = None

    def set_stage(self, stage: str) -> None:
        self.current_stage = stage

    def update_progress(self, current: int, total: int | None) -> None:
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
        self._overall_task = self._progress.add_task(f"[cyan]{label}", total=total)
        self._detail_task = self._progress.add_task("[magenta]Idle", total=None, visible=False)

    def set_podcast(self, name: str) -> None:
        super().set_podcast(name)
        self._progress.update(
            self._detail_task,
            visible=True,
            total=None,
            completed=0,
            description=f"[bold magenta]{name}",
        )

    def set_stage(self, stage: str) -> None:
        super().set_stage(stage)
        self._progress.update(
            self._detail_task,
            description=f"[bold magenta]{self.current_name}[/] [dim]{stage}[/]",
        )

    def update_progress(self, current: int, total: int | None) -> None:
        description = _render_stage_description(self.current_name, self.current_stage)
        self._progress.update(
            self._detail_task,
            description=f"[bold magenta]{description}",
            total=total,
            completed=current,
            visible=True,
        )

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

    return Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[bold]{task.description}"),
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
