"""Shared progress-callback type alias."""

from __future__ import annotations

from collections.abc import Callable

Callback = Callable[[int, int | None], None]
