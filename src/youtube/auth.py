from pathlib import Path
import sys
import os
from typing import Optional

sys.path.insert(0, Path(__file__).parent.parent.as_posix())
from src.models import YtDlpParams


def get_ydl_opts() -> YtDlpParams:
    """Get basic yt-dlp options without authentication"""
    return {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "socket_timeout": 30,
        "sleep_interval": 3,
        "max_sleep_interval": 8,
        "sleep_interval_requests": 1,
        "extractor_args": {"youtube": {"skip": ["js"]}},  # Skip JS-dependent formats
    }


def get_auth_ydl_opts(
    use_browser_fallback=False, prefer_native: bool = True
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
    if _apply_repo_cookiefile(opts, use_browser_fallback):
        return opts
    if use_browser_fallback:
        _apply_browser_fallback(opts, prefer_native)

    return opts


def _apply_authenticated_download_defaults(opts: YtDlpParams) -> None:
    opts["ratelimit"] = 2 * 1024 * 1024  # 2 MB/s — throttle media downloads only
    opts["js_runtimes"] = {"node": {}}


def _apply_cookiefile(
    opts: YtDlpParams,
    cookie_path: Path,
    success_message: str,
    invalid_message: str,
) -> bool:
    if cookie_path.exists() and cookie_path.stat().st_size > 0:
        opts["cookiefile"] = str(cookie_path)
        print(success_message.format(path=cookie_path))
        return True
    print(invalid_message.format(path=cookie_path))
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


def _apply_repo_cookiefile(
    opts: YtDlpParams, use_browser_fallback: bool
) -> bool:
    if use_browser_fallback:
        return False
    return _apply_cookiefile(
        opts,
        Path("cookies.txt"),
        "Using cookies file from: {path}",
        "WARNING: repo cookies file is invalid: {path}",
    )


def _apply_browser_fallback(opts: YtDlpParams, prefer_native: bool) -> None:
    if prefer_native:
        opts["cookiesfrombrowser"] = ("firefox",)
        print("Using Firefox browser cookies via yt-dlp browser fallback")
        return

    cookies_file = _try_export_firefox_cookies()
    if cookies_file is not None:
        opts["cookiefile"] = str(cookies_file)
        print(f"Using exported Firefox cookies file: {cookies_file}")
        return

    opts["cookiesfrombrowser"] = ("firefox",)
    print("Export failed; falling back to Firefox cookies via yt-dlp browser fallback")


def _try_export_firefox_cookies() -> Optional[Path]:
    """Attempt to export Firefox cookies for YouTube into a repo-local `cookies.txt`.

    Returns the Path to the cookies file on success, or None on failure.
    """
    browser_cookie3 = _import_browser_cookie3()
    if browser_cookie3 is None:
        return None

    cookie_jar = _load_firefox_cookie_jar(browser_cookie3)
    if cookie_jar is None:
        return None

    cookies_path = Path("cookies.txt")
    if _write_cookie_jar(cookies_path, cookie_jar):
        return cookies_path
    return None


def _import_browser_cookie3():
    try:
        import browser_cookie3
    except Exception:
        print("browser_cookie3 not available; cannot export Firefox cookies")
        return None
    return browser_cookie3


def _load_firefox_cookie_jar(browser_cookie3) -> object | None:
    try:
        return browser_cookie3.firefox(domain_name=".youtube.com")
    except TypeError:
        try:
            return browser_cookie3.firefox()
        except Exception as e:
            print(f"WARNING: Failed to load Firefox cookies: {e}")
            return None
    except Exception as e:
        print(f"WARNING: Failed to load Firefox cookies: {e}")
        return None


def _iter_cookie_jar(cookie_jar: object):
    cookies = getattr(cookie_jar, "cookies", None)
    return cookies or list(cookie_jar)


def _write_cookie_jar(cookies_path: Path, cookie_jar: object) -> bool:
    try:
        with cookies_path.open("w", encoding="utf-8") as fh:
            fh.write("# Netscape HTTP Cookie File\n")
            for cookie in _iter_cookie_jar(cookie_jar):
                fh.write(_format_cookie_line(cookie))
        return True
    except Exception as e:
        print(f"WARNING: Failed to write cookies file: {e}")
        return False


def _format_cookie_line(cookie: object) -> str:
    domain = cookie.domain
    flag = "TRUE" if domain.startswith(".") else "FALSE"
    path = cookie.path or "/"
    secure = "TRUE" if getattr(cookie, "secure", False) else "FALSE"
    expires = str(getattr(cookie, "expires", 0) or 0)
    name = cookie.name
    value = cookie.value
    return f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n"
