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

# ---------------------------------------------------------------------------
# rclone remote-control cache invalidation
# ---------------------------------------------------------------------------
# STORAGE_ROOT is written through this app's own rclone mount, not through the
# rclone serve http process that actually fronts RSS_BASE_URL -- that process
# keeps its own VFS cache and has no way to notice writes made outside it. If
# set, update_rss calls its remote-control API to forget the just-uploaded
# feed.rss so the change is visible immediately instead of waiting out the
# cache (or requiring a manual restart of that service).
RCLONE_RC_URL = os.getenv("RCLONE_RC_URL", "")
RCLONE_RC_USER = os.getenv("RCLONE_RC_USER", "")
RCLONE_RC_PASSWORD = os.getenv("RCLONE_RC_PASSWORD", "")
