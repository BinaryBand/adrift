"""Strict quality gate for Morbid alignment hard cases.

This pack intentionally mixes known-good matches with hard negatives from
audit output so matcher tuning can improve false-positive behavior without
regressing obvious positives.
"""

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adrift.core.models import AlignmentConfig, RssEpisode
from adrift.core.services.catalog import align_episodes_impl

_MORBID_ALIGNMENT = AlignmentConfig(extra_stopwords=["morbid"])
_HARD_PACK = (
    Path(__file__).resolve().parents[4] / "resources" / "alignment" / "morbid_hard_pack.csv"
)
_STRICT_MIN_PRECISION = 0.95
_STRICT_MAX_FALSE_POSITIVE_RATE = 0.05


@dataclass(frozen=True)
class _HardCase:
    should_match: bool
    reference_title: str
    download_title: str
