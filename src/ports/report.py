from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.models import MergeResult

ReportSection = Callable[[MergeResult], str]


@dataclass(frozen=True)
class ReportDocument:
    filename: str
    sections: tuple[ReportSection, ...]
    sep: str = "\n\n---\n\n"


@dataclass(frozen=True)
class ReportRenderOptions:
    documents: tuple[ReportDocument, ...] | None = None
    overwrite: bool = True


class ReportPort(Protocol):
    """Port for generating markdown reports from a MergeResult."""

    def generate_reports(
        self,
        result: MergeResult,
        output_root: Path,
        options: ReportRenderOptions | None = None,
    ) -> list[Path]:
        """Generate per-podcast report file(s); return created paths."""
        ...


def compose(
    result: MergeResult,
    sections: Sequence[ReportSection],
    sep: str = "\n\n---\n\n",
) -> str:
    return sep.join(s for section in sections if (s := section(result).strip()))
