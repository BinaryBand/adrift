import os

# ---------------------------------------------------------------------------
# RSS feed URL override
# ---------------------------------------------------------------------------
# When set, RSS enclosure URLs use this as the base instead of S3_ENDPOINT.
# Use this to expose files via a public tunnel while uploading to localhost.
# Example: RSS_BASE_URL=https://s3.example.com → enclosures resolve to
#   https://s3.example.com/media/podcasts/<show>/<episode>.opus
RSS_BASE_URL = os.getenv("RSS_BASE_URL", "")
