import shutil
from pathlib import Path
from types import SimpleNamespace

import src.web.rss as rss


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

    # Patch the module-level _rss_cache to return our dummy cache
    monkeypatch.setattr(rss, "_rss_cache", lambda: dummy)

    # Patch network/feedparser to avoid external calls
    class MockResponse:
        def __init__(self, text):
            self.text = text

    monkeypatch.setattr(
        rss,
        "requests",
        SimpleNamespace(get=lambda url, timeout=15: MockResponse("<rss/>")),
    )
    monkeypatch.setattr(
        rss, "feedparser", SimpleNamespace(parse=lambda s: SimpleNamespace(entries=[]))
    )

    # Call the function under test
    episodes = rss.get_rss_episodes("https://example.com/feed.xml")

    assert dummy.set_called is True
    assert isinstance(episodes, list)
