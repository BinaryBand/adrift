"""Context-scoped terminal message emitter shared across pipeline stages."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal, Protocol

Level = Literal["info", "warning", "error"]

_LEVEL_PREFIX: dict[Level, str] = {
    "info": "",
    "warning": "WARNING: ",
    "error": "ERROR: ",
}


class TerminalEmitter(Protocol):
    """Callable that renders a leveled message to the terminal."""

    def __call__(self, level: Level, message: str) -> None:
        """Emit ``message`` at ``level``."""
        ...


_EMITTER: ContextVar[TerminalEmitter | None] = ContextVar("terminal_emitter", default=None)


def _default_emit(level: Level, message: str) -> None:
    pass


def format_terminal_message(level: Level, message: str) -> str:
    """Return ``message`` prefixed with the marker for ``level``."""
    return f"{_LEVEL_PREFIX[level]}{message}"


def emit(level: Level, message: str) -> None:
    """Emit ``message`` at ``level`` via the active emitter, if any."""
    emitter = _EMITTER.get()
    if emitter is None:
        _default_emit(level, message)
        return
    emitter(level, message)


def emit_info(message: str) -> None:
    """Emit an info-level message."""
    emit("info", message)


def emit_warning(message: str) -> None:
    """Emit a warning-level message."""
    emit("warning", message)


def emit_error(message: str) -> None:
    """Emit an error-level message."""
    emit("error", message)


@contextmanager
def using_terminal_emitter(emitter: TerminalEmitter) -> Iterator[None]:
    """Bind ``emitter`` as the active terminal emitter for the duration."""
    token = _EMITTER.set(emitter)
    try:
        yield
    finally:
        _EMITTER.reset(token)
