from types import SimpleNamespace
from unittest.mock import patch

import pytest

from adrift.adapters import get_scored_alignment_adapter
from adrift.adapters.process.alignment import RustScoredAlignmentAdapter
from adrift.models.alignment_batch import AlignmentBatch, AlignmentBatchConfig


def _empty_batch() -> AlignmentBatch:
    return AlignmentBatch(
        config=AlignmentBatchConfig(
            id_weight=0.1,
            date_weight=0.3,
            title_weight=0.5,
            description_weight=0.1,
            date_score_tiers=((2, 1.0),),
            sparse_title_min=0.85,
            match_tolerance=0.75,
            title_certainty_min=0.97,
            metadata_rescue_subset_sim_min=0.78,
            containment_bonus=0.08,
            base_anchor_stopwords=(),
            extra_stopwords=(),
            numbered_marker_patterns=(),
        ),
        references=(),
        downloads=(),
    )


def test_factory_returns_rust_adapter_for_rust_backend() -> None:
    adapter = get_scored_alignment_adapter("rust")
    assert isinstance(adapter, RustScoredAlignmentAdapter)


def test_rust_adapter_uses_prototype_when_extension_missing() -> None:
    adapter = RustScoredAlignmentAdapter()
    result = adapter.align_batch(_empty_batch())
    assert result == ([], {})


def test_rust_adapter_raises_helpful_error_when_no_backend_is_available() -> None:
    adapter = RustScoredAlignmentAdapter()
    with patch(
        "adrift.adapters.process.alignment.rust_scored.import_module",
        side_effect=ModuleNotFoundError("missing"),
    ):
        with pytest.raises(RuntimeError, match="adrift_rust_alignment"):
            adapter.align_batch(_empty_batch())


def test_rust_adapter_uses_extension_align_batch_callable() -> None:
    expected = ([(0, 0)], {(0, 0): 0.99})
    fake_module = SimpleNamespace(align_batch=lambda batch: expected)
    adapter = RustScoredAlignmentAdapter()
    with patch("adrift.adapters.process.alignment.rust_scored.import_module") as mocked_import:
        mocked_import.return_value = fake_module
        result = adapter.align_batch(_empty_batch())
    assert result == expected
