"""Global application settings loaded from ``config/settings.toml``.

Values in the config file override the defaults defined below.  When the
config file is absent the defaults are used as-is, keeping the application
fully functional without any configuration file.
"""

import tomllib
from pathlib import Path
from typing import Any

_SETTINGS_PATH = Path("config/settings.toml")


def _load_settings() -> dict[str, Any]:
    if _SETTINGS_PATH.exists():
        with open(_SETTINGS_PATH, "rb") as f:
            return tomllib.load(f)
    return {}


_settings = _load_settings()
_matching: dict[str, Any] = _settings.get("matching", {})
_s3: dict[str, Any] = _settings.get("s3", {})

# ---------------------------------------------------------------------------
# Matching algorithm weights
# ---------------------------------------------------------------------------

MATCH_TOLERANCE: float = float(_matching.get("match_tolerance", 0.75))
W_ID: float = float(_matching.get("w_id", 0.10))
W_DATE: float = float(_matching.get("w_date", 0.30))
W_TITLE: float = float(_matching.get("w_title", 0.50))
W_DESC: float = float(_matching.get("w_desc", 0.10))
SPARSE_TITLE_MIN: float = float(_matching.get("sparse_title_min", 0.98))

DATE_SCORE_TIERS: tuple[tuple[int, float], ...] = tuple(
    (int(tier[0]), float(tier[1]))
    for tier in _matching.get("date_score_tiers", [(2, 1.00), (10, 0.70), (35, 0.15)])
)

# ---------------------------------------------------------------------------
# S3 / storage settings
# ---------------------------------------------------------------------------

PUBLIC_S3_URL: str = str(_s3.get("public_url", "")).strip()

__all__ = [
    "MATCH_TOLERANCE",
    "W_ID",
    "W_DATE",
    "W_TITLE",
    "W_DESC",
    "SPARSE_TITLE_MIN",
    "DATE_SCORE_TIERS",
    "PUBLIC_S3_URL",
]
