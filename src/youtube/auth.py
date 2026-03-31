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
    opts["ratelimit"] = 2 * 1024 * 1024  # 2 MB/s — throttle media downloads only

    # Prefer an explicitly set cookie file via env var
    env_cookie = os.getenv("YT_COOKIES_FILE")
    if env_cookie:
        cookie_path = Path(env_cookie)
        if cookie_path.exists() and cookie_path.stat().st_size > 0:
            opts["cookiefile"] = str(cookie_path)
            print(f"Using cookie file from: {cookie_path}")
            return opts
        else:
            print(f"WARNING: YT_COOKIES_FILE is invalid: {cookie_path}")

    # Try repo-local cookies.txt (only if browser fallback not explicitly requested)
    if not use_browser_fallback:
        cookies_path = Path("cookies.txt")
        if cookies_path.exists() and cookies_path.stat().st_size > 0:
            opts["cookiefile"] = str(cookies_path)
            print(f"Using cookies file from: {cookies_path}")
            return opts

    # Use browser login when requested or as fallback
    if use_browser_fallback:
        if prefer_native:
            # Prefer yt-dlp's native browser import (uses browser_cookie3 internally)
            opts["cookiesfrombrowser"] = ("firefox",)
            print("Using Firefox browser cookies via yt-dlp browser fallback")
        else:
            # Prefer exporting a cookies.txt file using browser_cookie3
            cookies_file = _try_export_firefox_cookies()
            if cookies_file:
                opts["cookiefile"] = str(cookies_file)
                print(f"Using exported Firefox cookies file: {cookies_file}")
            else:
                # Fallback to native option if export fails
                opts["cookiesfrombrowser"] = ("firefox",)
                print(
                    "Export failed; falling back to Firefox cookies via yt-dlp browser fallback"
                )

    return opts


def _try_export_firefox_cookies() -> Optional[Path]:
    """Attempt to export Firefox cookies for YouTube into a repo-local `cookies.txt`.

    Returns the Path to the cookies file on success, or None on failure.
    """
    try:
        import browser_cookie3
    except Exception:
        print("browser_cookie3 not available; cannot export Firefox cookies")
        return None

    try:
        # Load Firefox cookies; limit to YouTube-related domains for smaller file
        cj = browser_cookie3.firefox(domain_name=".youtube.com")
    except TypeError:
        # Older versions expect no args
        try:
            cj = browser_cookie3.firefox()
        except Exception as e:
            print(f"WARNING: Failed to load Firefox cookies: {e}")
            return None
    except Exception as e:
        print(f"WARNING: Failed to load Firefox cookies: {e}")
        return None

    cookies_path = Path("cookies.txt")
    try:
        with cookies_path.open("w", encoding="utf-8") as fh:
            fh.write("# Netscape HTTP Cookie File\n")
            # browser_cookie3 returns a CookieJar; iterate over cookies
            for cookie in getattr(cj, "cookies", []) or list(cj):
                domain = cookie.domain
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                path = cookie.path or "/"
                secure = "TRUE" if getattr(cookie, "secure", False) else "FALSE"
                expires = str(getattr(cookie, "expires", 0) or 0)
                name = cookie.name
                value = cookie.value
                fh.write(
                    f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n"
                )
        return cookies_path
    except Exception as e:
        print(f"WARNING: Failed to write cookies file: {e}")
        return None
