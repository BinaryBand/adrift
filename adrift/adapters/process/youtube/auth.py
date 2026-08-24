"""YouTube authentication and yt-dlp options helpers."""

import importlib
import os
import shutil
from pathlib import Path
from typing import Any

from adrift.core.models import YtDlpParams
from adrift.core.util.terminal import emit_info, emit_warning


class _QuietYtDlpLogger:
    def debug(self, _msg: str) -> None:
        return

    def warning(self, _msg: str) -> None:
        return

    def error(self, _msg: str) -> None:
        return


_QUIET_YTDLP_LOGGER = _QuietYtDlpLogger()

_COOKIE_IMPORT_ERRORS = (ImportError, ModuleNotFoundError)
_COOKIE_LOAD_ERRORS = (AttributeError, OSError, RuntimeError, ValueError)
_COOKIE_WRITE_ERRORS = (AttributeError, OSError, TypeError, ValueError)


def _node_path() -> str | None:
    return shutil.which("node")


def get_ydl_opts() -> YtDlpParams:
    """Get basic yt-dlp options without authentication."""
    return YtDlpParams.model_validate(
        {
            "quiet": True,
            "no_warnings": True,
            "logger": _QUIET_YTDLP_LOGGER,
            "extract_flat": False,
            "socket_timeout": 30,
            "sleep_interval": 3,
            "max_sleep_interval": 8,
            "sleep_interval_requests": 1,
            "extractor_args": {"youtube": {"skip": ["js"]}},  # Skip JS-dependent formats
        }
    )


def get_auth_ydl_opts(
    *, use_browser_fallback: bool = False, prefer_native: bool = True
) -> YtDlpParams:
    """Get yt-dlp options with cookie authentication and optional browser fallback.

    Args:
        use_browser_fallback: when True, enable browser-based authentication.
        prefer_native: when True prefer yt-dlp's `cookiesfrombrowser` option; when
            False prefer exporting a `cookies.txt` file via `browser_cookie3`.
    """
    opts = get_ydl_opts()
    _apply_authenticated_download_defaults(opts)

    if _apply_env_cookiefile(opts):
        return opts
    if not use_browser_fallback and _apply_repo_cookiefile(opts):
        return opts
    if use_browser_fallback:
        _apply_browser_fallback(opts, prefer_native)

    return opts


def _apply_authenticated_download_defaults(opts: YtDlpParams) -> None:
    opts.ratelimit = 2 * 1024 * 1024  # 2 MB/s — throttle media downloads only
    # Provide Node.js so yt-dlp can solve YouTube's n-challenge (required for
    # age-restricted and some other videos). remote_components lets it fetch the
    # challenge solver script from GitHub on first use.
    node = _node_path()
    opts.js_runtimes = {"node": {"path": node} if node else {}}
    opts.remote_components = {"ejs:github"}
    # Age-restricted videos require JS for auth token verification; remove the
    # skip that get_ydl_opts sets for unauthenticated use.
    opts.extractor_args = {"youtube": {}}


def _apply_cookiefile(
    opts: YtDlpParams,
    cookie_path: Path,
    success_message: str,
    invalid_message: str,
) -> bool:
    try:
        if cookie_path.stat().st_size > 0:
            opts.cookiefile = str(cookie_path)
            emit_info(success_message.format(path=cookie_path))
            return True
    except FileNotFoundError:
        pass
    emit_warning(invalid_message.format(path=cookie_path).removeprefix("WARNING: "))
    return False


def _apply_env_cookiefile(opts: YtDlpParams) -> bool:
    env_cookie = os.getenv("YT_COOKIES_FILE")
    if not env_cookie:
        return False
    return _apply_cookiefile(
        opts,
        Path(env_cookie),
        "Using cookie file from: {path}",
        "WARNING: YT_COOKIES_FILE is invalid: {path}",
    )


def _apply_repo_cookiefile(opts: YtDlpParams) -> bool:
    return _apply_cookiefile(
        opts,
        Path("cookies.txt"),
        "Using cookie file from: {path}",
        "WARNING: repo cookies file is invalid: {path}",
    )


# Locations yt-dlp searches for a Firefox profile. If none of them holds a
# cookie database there are no browser cookies to read, and pointing yt-dlp at
# them anyway aborts the whole attempt instead of proceeding unauthenticated.
_FIREFOX_PROFILE_DIRS = (
    "~/.mozilla/firefox",
    "~/.config/mozilla/firefox",
    "~/snap/firefox/common/.mozilla/firefox",
    "~/.var/app/org.mozilla.firefox/.mozilla/firefox",
    "~/.var/app/org.mozilla.firefox/config/mozilla/firefox",
)


def _firefox_profile_available() -> bool:
    """Return True if a Firefox cookie database exists on this host.

    The profile directory alone is not enough: a Firefox install that has never
    run leaves behind crash-report folders but no ``cookies.sqlite``.
    """
    for directory in _FIREFOX_PROFILE_DIRS:
        root = Path(directory).expanduser()
        if not root.is_dir():
            continue
        if (root / "cookies.sqlite").is_file():
            return True
        if any(root.glob("*/cookies.sqlite")):
            return True
    return False


def _apply_browser_fallback(opts: YtDlpParams, prefer_native: bool) -> None:  # noqa: FBT001
    if not _firefox_profile_available():
        # Leave cookies unset. The attempt still gets the Node JS runtime and
        # the relaxed extractor args, which is enough for public videos.
        # Setting cookiesfrombrowser here would fail the attempt outright, and
        # that failure is not classified retryable, so it would abort the whole
        # ladder before the alternate player clients ever get a turn.
        emit_warning("No Firefox profile found; continuing without browser cookies")
        return

    if prefer_native:
        opts.cookiesfrombrowser = ("firefox",)
        emit_info("Using Firefox browser cookies via yt-dlp browser fallback")
        return

    cookies_file = _try_export_firefox_cookies()
    if cookies_file is not None:
        opts.cookiefile = str(cookies_file)
        emit_info(f"Using exported Firefox cookies file: {cookies_file}")
        return

    if not _firefox_profile_available():
        emit_warning("Export failed and no Firefox profile found; continuing without cookies")
        return

    opts.cookiesfrombrowser = ("firefox",)
    emit_warning("Export failed; falling back to Firefox cookies via yt-dlp browser fallback")


def _try_export_firefox_cookies() -> Path | None:
    """Attempt to export Firefox cookies for YouTube into a repo-local `cookies.txt`.

    Returns the Path to the cookies file on success, or None on failure.
    """
    try:
        browser_cookie3 = importlib.import_module("browser_cookie3")
    except _COOKIE_IMPORT_ERRORS:
        emit_warning("browser_cookie3 not available; cannot export Firefox cookies")
        return None

    cookie_jar = _load_firefox_cookie_jar(browser_cookie3)
    if cookie_jar is None:
        return None

    cookies_path = Path("cookies.txt")
    if _write_cookie_jar(cookies_path, cookie_jar):
        return cookies_path
    return None


def _load_firefox_cookie_jar(browser_cookie3: Any) -> Any | None:  # noqa: ANN401
    try:
        return browser_cookie3.firefox(domain_name=".youtube.com")
    except TypeError as e:
        if "domain_name" not in str(e):
            emit_warning(f"Failed to load Firefox cookies: {e}")
            return None
        # Older browser_cookie3 versions don't accept domain_name — retry without it
        try:
            return browser_cookie3.firefox()
        except _COOKIE_LOAD_ERRORS as e2:
            emit_warning(f"Failed to load Firefox cookies: {e2}")
            return None
    except _COOKIE_LOAD_ERRORS as e:
        emit_warning(f"Failed to load Firefox cookies: {e}")
        return None


def _write_cookie_jar(cookies_path: Path, cookie_jar: Any) -> bool:  # noqa: ANN401
    try:
        fd = os.open(cookies_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("# Netscape HTTP Cookie File\n")
            for cookie in cookie_jar:
                fh.write(_format_cookie_line(cookie))
    except _COOKIE_WRITE_ERRORS as e:
        emit_warning(f"Failed to write cookies file: {e}")
        return False
    else:
        return True


def _format_cookie_line(cookie: Any) -> str:  # noqa: ANN401
    domain = _sanitize(cookie.domain)
    flag = "TRUE" if domain.startswith(".") else "FALSE"
    path = _sanitize(cookie.path or "/")
    secure = "TRUE" if getattr(cookie, "secure", False) else "FALSE"
    expires = str(getattr(cookie, "expires", 0) or 0)
    name = _sanitize(cookie.name)
    value = _sanitize(cookie.value)
    return f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n"


def _sanitize(s: str) -> str:
    return s.replace("\t", " ").replace("\n", " ").replace("\r", " ")
