import os

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
