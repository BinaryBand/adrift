from __future__ import annotations

import sys
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Literal, Protocol

Level = Literal["info", "warning", "error"]

_LEVEL_PREFIX: dict[Level, str] = {
    "info": "",
    "warning": "WARNING: ",
    "error": "ERROR: ",
}


class TerminalEmitter(Protocol):
    def __call__(self, level: Level, message: str) -> None: ...


_EMITTER: ContextVar[TerminalEmitter | None] = ContextVar("terminal_emitter", default=None)


def _default_emit(level: Level, message: str) -> None:
    print(format_terminal_message(level, message), file=sys.stderr)


def format_terminal_message(level: Level, message: str) -> str:
    return f"{_LEVEL_PREFIX[level]}{message}"


def emit(level: Level, message: str) -> None:
    emitter = _EMITTER.get()
    if emitter is None:
        _default_emit(level, message)
        return
    emitter(level, message)


def emit_info(message: str) -> None:
    emit("info", message)


def emit_warning(message: str) -> None:
    emit("warning", message)


def emit_error(message: str) -> None:
    emit("error", message)


@contextmanager
def using_terminal_emitter(emitter: TerminalEmitter) -> Iterator[None]:
    token = _EMITTER.set(emitter)
    try:
        yield
    finally:
        _EMITTER.reset(token)
