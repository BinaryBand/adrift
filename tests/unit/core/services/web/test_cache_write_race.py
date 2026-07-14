import shutil
from pathlib import Path
from types import SimpleNamespace

from adrift.adapters.process.episode_sources import episode_source_rss as rss


def test_cache_set_with_retry_retries_and_recreates_dir(tmp_path):
    calls = []

    class DummyCache:
        def __init__(self, directory):
            self.directory = str(directory)

        def set(self, key, value, expire=None):
            calls.append((key, value, expire))
            # Fail the first time to simulate the diskcache FileNotFoundError
            if len(calls) == 1:
                raise FileNotFoundError("simulated nested write failure")
            return True

    dummy = DummyCache(tmp_path / "rss")
    base = Path(dummy.directory)
    # Ensure the directory does not exist before the call
    if base.exists():
        shutil.rmtree(base)

    # Should retry and create the directory
    rss._cache_set_with_retry(dummy, "key", "value", expire=60)

    assert len(calls) == 2
    assert base.exists()


def test_get_rss_episodes_calls_cache_set(tmp_path, monkeypatch):
    class DummyCache:
        def __init__(self):
            self.directory = str(tmp_path / "rss2")
            Path(self.directory).mkdir(parents=True, exist_ok=True)
            self.set_called = False

        def get(self, key):
            return None

        def set(self, key, value, expire=None):
            self.set_called = True

    dummy = DummyCache()

    # Patch both cache object and wrapper used by `_cache_set_with_retry`.
    monkeypatch.setattr(rss, "_RSS_CACHE", dummy)
    monkeypatch.setattr(rss, "_RSS_CACHE_WRAPPER", rss.RaceAwareCacheWrapper(dummy))

    # Patch network/feedparser to avoid external calls
    class MockResponse:
        def __init__(self, text):
            self.text = text
            self.status_code = 200
            self.headers = {}

        def raise_for_status(self):
            return None

    def fake_get(url, timeout=15, headers=None):
        del url, timeout, headers
        return MockResponse("<rss/>")

    monkeypatch.setattr(rss, "requests", SimpleNamespace(get=fake_get))
    monkeypatch.setattr(
        rss, "feedparser", SimpleNamespace(parse=lambda s: SimpleNamespace(entries=[]))
    )

    # Call the function under test
    episodes = rss.get_rss_episodes("https://example.com/feed.xml")

    assert dummy.set_called is True
    assert isinstance(episodes, list)


def test_fetch_rss_feed_str_uses_conditional_headers_on_304(monkeypatch):
    cached_payload = {
        "feed_str": "<rss/>",
        "etag": '"abc123"',
        "last_modified": "Mon, 01 Jan 2024 00:00:00 GMT",
    }
    requested_headers: list[dict[str, str]] = []

    class DummyCache:
        def get(self, key):
            return cached_payload

        def set(self, key, value, expire=None):
            raise AssertionError("cache write not expected on 304")

    class MockResponse:
        def __init__(self, status_code: int):
            self.status_code = status_code
            self.text = ""
            self.headers: dict[str, str] = {}

        def raise_for_status(self):
            return None

    def fake_get(url, timeout=15, headers=None):
        del url, timeout
        requested_headers.append(headers or {})
        return MockResponse(304)

    monkeypatch.setattr(rss, "_RSS_CACHE", DummyCache())
    monkeypatch.setattr(rss, "_RSS_CACHE_WRAPPER", rss.RaceAwareCacheWrapper(DummyCache()))
    monkeypatch.setattr(rss, "requests", SimpleNamespace(get=fake_get))

    feed_str = rss._fetch_rss_feed_str("https://example.com/feed.xml")

    assert feed_str == "<rss/>"
    assert requested_headers == [
        {
            "If-None-Match": '"abc123"',
            "If-Modified-Since": "Mon, 01 Jan 2024 00:00:00 GMT",
        }
    ]
