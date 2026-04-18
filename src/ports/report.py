from collections.abc import Callable

from src.models.pipeline import MergeResult

ReportSection = Callable[[MergeResult], str]


def compose(
    result: MergeResult,
    sections: list[ReportSection],
    sep: str = "\n\n---\n\n",
) -> str:
    return sep.join(s for section in sections if (s := section(result).strip()))
