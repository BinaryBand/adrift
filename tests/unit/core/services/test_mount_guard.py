"""Tests for the rclone pCloud mount-point guard."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from adrift.core.services.mount_guard import (
    _find_mount_point,
    _is_rclone_pcloud_mount,
    _parse_mount_entry,
    ensure_rclone_pcloud_mount,
)

_PROCFS_PCLOUD = (
    "sysfs /sys sysfs rw,nosuid,nodev 0 0\n"
    "pcloud:Podcasts /mnt/pcloud fuse.rclone rw,nosuid,nodev 0 0\n"
    "tmpfs /tmp tmpfs rw,nosuid,nodev 0 0\n"
)

_PROCFS_NON_PCLOUD_RCLONE = (
    "sysfs /sys sysfs rw,nosuid,nodev 0 0\n"
    "gdrive:Stuff /mnt/gdrive fuse.rclone rw,nosuid,nodev 0 0\n"
    "tmpfs /tmp tmpfs rw,nosuid,nodev 0 0\n"
)

_PROCFS_NO_RCLONE = (
    "sysfs /sys sysfs rw,nosuid,nodev 0 0\n"
    "tmpfs /tmp tmpfs rw,nosuid,nodev 0 0\n"
    "/dev/sda1 / ext4 rw,relatime 0 0\n"
)


class TestParseMountEntry:
    def test_finds_existing_mount_point(self) -> None:
        with patch("pathlib.Path.open", mock_open(read_data=_PROCFS_PCLOUD)):
            entry = _parse_mount_entry(Path("/mnt/pcloud"))
        assert entry == ("pcloud:Podcasts", "fuse.rclone")

    def test_returns_none_for_unknown_mount(self) -> None:
        with patch("pathlib.Path.open", mock_open(read_data=_PROCFS_PCLOUD)):
            assert _parse_mount_entry(Path("/nonexistent")) is None

    def test_returns_none_when_proc_mounts_unreadable(self) -> None:
        with patch("pathlib.Path.open", side_effect=OSError):
            assert _parse_mount_entry(Path("/mnt/pcloud")) is None


class TestIsRclonePcloud:
    def test_true_for_pcloud_rclone_mount(self) -> None:
        with patch("pathlib.Path.open", mock_open(read_data=_PROCFS_PCLOUD)):
            assert _is_rclone_pcloud_mount(Path("/mnt/pcloud")) is True

    def test_false_for_non_pcloud_rclone_mount(self) -> None:
        with patch("pathlib.Path.open", mock_open(read_data=_PROCFS_NON_PCLOUD_RCLONE)):
            assert _is_rclone_pcloud_mount(Path("/mnt/gdrive")) is False

    def test_false_for_non_rclone_mount(self) -> None:
        with patch("pathlib.Path.open", mock_open(read_data=_PROCFS_NO_RCLONE)):
            assert _is_rclone_pcloud_mount(Path("/")) is False

    def test_false_for_unmounted_path(self) -> None:
        with patch("pathlib.Path.open", mock_open(read_data=_PROCFS_PCLOUD)):
            assert _is_rclone_pcloud_mount(Path("/nonexistent")) is False


class TestFindMountPoint:
    def test_returns_mount_point_for_nested_path(self) -> None:
        with patch("os.path.ismount", side_effect=lambda p: str(p) == "/mnt/pcloud"):
            result = _find_mount_point(Path("/mnt/pcloud/sub/deep"))
        assert result == Path("/mnt/pcloud")

    def test_returns_none_when_no_mount_found(self) -> None:
        with patch("os.path.ismount", return_value=False):
            assert _find_mount_point(Path("/mnt/pcloud/sub")) is None

    def test_path_itself_is_mount_point(self) -> None:
        with patch("os.path.ismount", return_value=True):
            result = _find_mount_point(Path("/mnt/pcloud"))
        assert result == Path("/mnt/pcloud")


class TestEnsureRclonePcloudMount:
    def test_bypass_with_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ADRIFT_ALLOW_LOCAL_WRITES", "1")
        ensure_rclone_pcloud_mount("/tmp")  # should not raise

    def test_hard_fails_when_no_mount_point(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ADRIFT_ALLOW_LOCAL_WRITES", raising=False)
        with (
            patch("os.path.ismount", return_value=False),
            pytest.raises(RuntimeError, match="not on a mounted filesystem"),
        ):
            ensure_rclone_pcloud_mount("/tmp")

    def test_hard_fails_when_not_rclone_pcloud(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ADRIFT_ALLOW_LOCAL_WRITES", raising=False)
        with (
            patch("os.path.ismount", return_value=True),
            patch("pathlib.Path.open", mock_open(read_data=_PROCFS_NO_RCLONE)),
            pytest.raises(RuntimeError, match="not an rclone pCloud mount"),
        ):
            ensure_rclone_pcloud_mount("/tmp")

    def test_passes_for_valid_pcloud_mount(self) -> None:
        with (
            patch("os.path.ismount", return_value=True),
            patch("pathlib.Path.open", mock_open(read_data=_PROCFS_PCLOUD)),
        ):
            ensure_rclone_pcloud_mount("/mnt/pcloud")  # should not raise

    def test_custom_env_var_appears_in_error_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ADRIFT_ALLOW_LOCAL_WRITES", raising=False)
        with (
            patch("os.path.ismount", return_value=False),
            pytest.raises(RuntimeError, match="ADRIFT_OUTPUT_DIR"),
        ):
            ensure_rclone_pcloud_mount("/tmp", env_var="ADRIFT_OUTPUT_DIR")

    def test_resolves_relative_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ADRIFT_ALLOW_LOCAL_WRITES", raising=False)
        with (
            patch("os.path.ismount", return_value=False),
            pytest.raises(RuntimeError),
        ):
            ensure_rclone_pcloud_mount("./downloads")
