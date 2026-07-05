import os

# ---------------------------------------------------------------------------
# Local storage root
# ---------------------------------------------------------------------------
# Root directory for storage writes: files land at <STORAGE_ROOT>/<bucket>/<key>.
# In production this is expected to be an rclone mount point; rclone's
# sync-to-remote and any public serving are handled entirely outside this
# application.
STORAGE_ROOT = os.getenv("STORAGE_ROOT", "./storage")

# ---------------------------------------------------------------------------
# RSS feed URL override
# ---------------------------------------------------------------------------
# Base URL used to build RSS enclosure links for files under STORAGE_ROOT.
# Required wherever RSS feeds are generated -- there is no fallback endpoint.
# Example: RSS_BASE_URL=https://cdn.example.com → enclosures resolve to
#   https://cdn.example.com/media/podcasts/<show>/<episode>.opus
RSS_BASE_URL = os.getenv("RSS_BASE_URL", "")
