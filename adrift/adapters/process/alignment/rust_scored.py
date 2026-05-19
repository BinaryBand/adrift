from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Callable, cast

from adrift.models.alignment_batch import AlignmentBatch

_EXTENSION_MODULE = "adrift_rust_alignment"


class RustScoredAlignmentAdapter:
    """Batch-oriented scored aligner backed by an optional Rust extension."""

    def __init__(self) -> None:
        self._align_batch_fn: _AlignBatchFn | None = None

    def align_batch(
        self,
        batch: AlignmentBatch,
    ) -> tuple[list[tuple[int, int]], dict[tuple[int, int], float]]:
        return self._resolved_align_batch_fn()(batch)

    def _resolved_align_batch_fn(self) -> "_AlignBatchFn":
        if self._align_batch_fn is None:
            self._align_batch_fn = _load_extension_align_batch_fn()
        return self._align_batch_fn


_AlignBatchFn = Callable[
    [AlignmentBatch],
    tuple[list[tuple[int, int]], dict[tuple[int, int], float]],
]


def _load_extension_align_batch_fn() -> _AlignBatchFn:
    module = _load_extension_module()
    candidate = getattr(module, "align_batch", None)
    if callable(candidate):
        return cast(_AlignBatchFn, candidate)
    raise RuntimeError(
        "Rust alignment backend is missing required callable 'align_batch' "
        f"in module '{_EXTENSION_MODULE}'."
    )


def _load_extension_module() -> ModuleType:
    try:
        return import_module(_EXTENSION_MODULE)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Rust alignment backend requested but extension module "
            f"'{_EXTENSION_MODULE}' is not installed."
        ) from exc


__all__ = ["RustScoredAlignmentAdapter"]