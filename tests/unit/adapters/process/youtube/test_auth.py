"""Cover the Firefox-profile guard on the browser cookie fallback.

The guard exists because a host with no Firefox profile -- the `diot` service
account that runs the scheduled download -- made yt-dlp raise "could not find
firefox cookies database", which aborted the whole retry ladder.
"""

import pytest

from adrift.adapters.process.youtube import auth
from adrift.core.models import YtDlpParams


def _profile_root(tmp_path, name: str):
    root = tmp_path / name
    root.mkdir(parents=True)
    return root


def test_profile_unavailable_when_no_directory_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "_FIREFOX_PROFILE_DIRS", (str(tmp_path / "absent"),))
    assert auth._firefox_profile_available() is False


def test_profile_unavailable_when_directory_has_no_cookie_database(tmp_path, monkeypatch):
    """A Firefox that has never run leaves folders behind but no cookies.sqlite."""
    root = _profile_root(tmp_path, "firefox")
    (root / "Crash Reports").mkdir()
    monkeypatch.setattr(auth, "_FIREFOX_PROFILE_DIRS", (str(root),))
    assert auth._firefox_profile_available() is False


def test_profile_found_directly_in_root(tmp_path, monkeypatch):
    root = _profile_root(tmp_path, "firefox")
    (root / "cookies.sqlite").touch()
    monkeypatch.setattr(auth, "_FIREFOX_PROFILE_DIRS", (str(root),))
    assert auth._firefox_profile_available() is True


def test_profile_found_one_level_down(tmp_path, monkeypatch):
    """The real layout is <root>/<profile>.default/cookies.sqlite."""
    root = _profile_root(tmp_path, "firefox")
    profile = root / "5i4pnss1.default"
    profile.mkdir()
    (profile / "cookies.sqlite").touch()
    monkeypatch.setattr(auth, "_FIREFOX_PROFILE_DIRS", (str(root),))
    assert auth._firefox_profile_available() is True


@pytest.mark.parametrize("prefer_native", [True, False])
def test_browser_fallback_sets_no_cookies_without_a_profile(monkeypatch, prefer_native):
    """Both branches must leave cookies unset, not just the native one."""
    monkeypatch.setattr(auth, "_firefox_profile_available", lambda: False)
    opts = YtDlpParams()

    auth._apply_browser_fallback(opts, prefer_native)

    assert opts.cookiesfrombrowser is None
    assert opts.cookiefile is None


def test_browser_fallback_uses_firefox_when_a_profile_exists(monkeypatch):
    monkeypatch.setattr(auth, "_firefox_profile_available", lambda: True)
    opts = YtDlpParams()

    auth._apply_browser_fallback(opts, prefer_native=True)

    assert opts.cookiesfrombrowser == ("firefox",)
