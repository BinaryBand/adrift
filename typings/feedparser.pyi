from typing import Any, Dict, List


class FeedParserDict(Dict[str, Any]):
    bozo: bool
    feed: 'FeedParserDict'
    entries: List['FeedParserDict']


def parse(url: str) -> FeedParserDict: ...
