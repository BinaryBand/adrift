from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.models import MergeResult


@dataclass(frozen=True)
class MermaidRenderOptions:
    filename: str | None = None
    format: str = "sankey"
    overwrite: bool = True


class MermaidPort(Protocol):
    """Port for generating Mermaid diagrams from a MergeResult."""

    def generate_diagrams(
        self,
        result: MergeResult,
        output_root: Path,
        options: MermaidRenderOptions | None = None,
    ) -> list[Path]:
        """Generate per-podcast Mermaid diagram file(s); return created paths."""
        ...
