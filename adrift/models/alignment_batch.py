from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AlignmentEpisodeRecord:
    """Rust-friendly episode row with pre-cleaned fields."""

    episode_id: str
    normalized_title: str
    normalized_description: str
    pub_date_unix_s: int | None


@dataclass(frozen=True, slots=True)
class AlignmentBatchConfig:
    """Flattened alignment settings for a batch scorer."""

    id_weight: float
    date_weight: float
    title_weight: float
    description_weight: float
    date_score_tiers: tuple[tuple[int, float], ...]
    sparse_title_min: float
    match_tolerance: float
    title_certainty_min: float
    metadata_rescue_subset_sim_min: float
    containment_bonus: float
    base_anchor_stopwords: tuple[str, ...]
    extra_stopwords: tuple[str, ...]
    numbered_marker_patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AlignmentBatch:
    """Bulk alignment payload ready for a Rust scorer."""

    config: AlignmentBatchConfig
    references: tuple[AlignmentEpisodeRecord, ...]
    downloads: tuple[AlignmentEpisodeRecord, ...]


__all__ = [
    "AlignmentBatch",
    "AlignmentBatchConfig",
    "AlignmentEpisodeRecord",
]
