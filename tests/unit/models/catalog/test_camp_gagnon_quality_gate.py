"""Quality gate for Camp Gagnon alignment using reviewed CSV fixtures.

This test intentionally encodes current expectations:
- reviewed/confirmed rows should align
- rows marked false_positive should not align
"""

from __future__ import annotations

import csv
import math
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pytest

from adrift.models import AlignmentConfig, RssEpisode
from adrift.services.app_common import load_podcasts_config
from adrift.services.catalog import align_episodes_impl

REPO_ROOT = Path(__file__).resolve().parents[4]
SOURCE_TO_REF_CSV = REPO_ROOT / "docs" / ".dev" / "source_to_ref.csv"
FOR_REVIEW_CSV = REPO_ROOT / "docs" / ".dev" / "for_review.csv"
FIXED_PUB_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
# Current best-achieved floor with this scorer/config family is ~95%.
_MIN_CONFIRMED_POSITIVE_MATCH_RATE = 0.95

_FIXTURES_AVAILABLE = SOURCE_TO_REF_CSV.exists() and FOR_REVIEW_CSV.exists()
_skip_without_fixtures = pytest.mark.skipif(
    not _FIXTURES_AVAILABLE,
    reason="Local dev CSV fixtures not present (docs/.dev/); skipped in CI.",
)

