import os

# ---------------------------------------------------------------------------
# Episode alignment weights
# ---------------------------------------------------------------------------
# These four weights must sum to 1.0 (ID is applied as an additive bonus).
W_ID = 0.10
W_DATE = 0.30
W_TITLE = 0.50
W_DESC = 0.10

# Tiered date-similarity scoring: (max_days_delta, score)
DATE_SCORE_TIERS: tuple[tuple[int, float], ...] = ((2, 1.00), (10, 0.70), (35, 0.15))

# Minimum title similarity required when episode has no description or date signal.
SPARSE_TITLE_MIN = 0.98

# ---------------------------------------------------------------------------
# Match tolerance
# ---------------------------------------------------------------------------
# Pairs whose combined score falls below this threshold are discarded.
MATCH_TOLERANCE = 0.75

# ---------------------------------------------------------------------------
# RSS feed URL override
# ---------------------------------------------------------------------------
# When set, RSS enclosure URLs use this as the base instead of S3_ENDPOINT.
# Use this to expose files via a public tunnel while uploading to localhost.
# Example: RSS_BASE_URL=https://s3.example.com → enclosures resolve to
#   https://s3.example.com/media/podcasts/<show>/<episode>.opus
RSS_BASE_URL = os.getenv("RSS_BASE_URL", "")
