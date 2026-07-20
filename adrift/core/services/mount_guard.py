"""Mount-point guard — prevents writes to local drives.

Every storage write (audio files via STORAGE_ROOT, merge output via
--output-dir) must target an rclone FUSE mount to pCloud. This module
provides a single check that hard-fails when a path is local.

Set ADRIFT_ALLOW_LOCAL_WRITES=1 to bypass (dev/testing escape hatch).
"""

from __future__ import annotations

import os
from pathlib import Path


def _find_mount_point(path: Path) -> Path | None:
    """Walk up from *path* and return the first mount point, or None."""
    resolved = path.resolve()
    candidate = resolved
    while True:
        if os.path.ismount(str(candidate)):
            return candidate
        parent = candidate.parent
        if parent == candidate:
            return None
        candidate = parent


_MOUNT_ENTRY_MIN_FIELDS = 3


def _parse_mount_entry(mount_point: Path) -> tuple[str, str] | None:
    """Return (source, fstype) for *mount_point* from /proc/mounts, or None."""
    try:
        with Path("/proc/mounts").open() as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= _MOUNT_ENTRY_MIN_FIELDS and parts[1] == str(mount_point):
                    return parts[0], parts[2]
    except OSError:
        pass
    return None


def _is_rclone_pcloud_mount(mount_point: Path) -> bool:
    """Return True if *mount_point* is an rclone FUSE mount targeting pCloud."""
    entry = _parse_mount_entry(mount_point)
    if entry is None:
        return False
    source, fstype = entry
    if fstype != "fuse.rclone":
        return False
    return source.startswith("pcloud")


def ensure_rclone_pcloud_mount(path: str | Path, env_var: str = "STORAGE_ROOT") -> None:
    """Raise RuntimeError if *path* does not reside on an rclone pCloud mount.

    Set ``ADRIFT_ALLOW_LOCAL_WRITES=1`` in the environment to bypass this check
    entirely (useful for local development and testing).
    """
    if os.getenv("ADRIFT_ALLOW_LOCAL_WRITES") == "1":
        return

    resolved = Path(path).resolve()
    mount_point = _find_mount_point(resolved)

    if mount_point is None:
        msg = (
            f"{env_var}={path} is not on a mounted filesystem. "
            "It must be an rclone pCloud mount. "
            "Set ADRIFT_ALLOW_LOCAL_WRITES=1 to bypass."
        )
        raise RuntimeError(msg)

    if not _is_rclone_pcloud_mount(mount_point):
        msg = (
            f"{env_var}={path} (mount point: {mount_point}) "
            "is not an rclone pCloud mount. "
            "Downloads and output must target a pCloud rclone mount. "
            "Set ADRIFT_ALLOW_LOCAL_WRITES=1 to bypass."
        )
        raise RuntimeError(msg)


__all__ = ["ensure_rclone_pcloud_mount"]
