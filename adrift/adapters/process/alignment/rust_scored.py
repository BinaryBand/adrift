from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import TYPE_CHECKING, cast

from adrift.core.models.alignment_batch import AlignmentBatch
from adrift.core.util.alignment_pairs import AlignmentResult

if TYPE_CHECKING:
    from types import ModuleType

_EXTENSION_MODULE = "adrift_rust_alignment"
_PROTOTYPE_MODULE = "adrift.adapters.process.alignment.rust_prototype"


class RustScoredAlignmentAdapter:
    """Batch-oriented scored aligner backed by an optional Rust extension."""

    def __init__(self) -> None:
        self._align_batch_fn: _AlignBatchFn | None = None

    def align_batch(
        self,
        batch: AlignmentBatch,
    ) -> AlignmentResult:
        return self._resolved_align_batch_fn()(batch)

    def _resolved_align_batch_fn(self) -> _AlignBatchFn:
        if self._align_batch_fn is None:
            self._align_batch_fn = _load_extension_align_batch_fn()
        return self._align_batch_fn


_AlignBatchFn = Callable[
    [AlignmentBatch],
    AlignmentResult,
]


def _load_extension_align_batch_fn() -> _AlignBatchFn:
    module = _load_extension_module()
    candidate = getattr(module, "align_batch", None)
    if callable(candidate):
        return cast("_AlignBatchFn", candidate)
    msg = (
        "Rust alignment backend is missing required callable 'align_batch' "
        f"in module '{_EXTENSION_MODULE}'."
    )
    raise RuntimeError(msg)


def _load_extension_module() -> ModuleType:
    try:
        return import_module(_EXTENSION_MODULE)
    except ModuleNotFoundError as exc:
        return _load_prototype_module(exc)


def _load_prototype_module(cause: ModuleNotFoundError) -> ModuleType:
    try:
        return import_module(_PROTOTYPE_MODULE)
    except ModuleNotFoundError as exc:
        msg = (
            "Rust alignment backend requested but extension module "
            f"'{_EXTENSION_MODULE}' is not installed, and prototype module "
            f"'{_PROTOTYPE_MODULE}' was not found."
        )
        raise RuntimeError(msg) from exc


__all__ = ["RustScoredAlignmentAdapter"]
