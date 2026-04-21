from src.adapters.mermaid import build_sankey_lines
from src.models import MergeResult

from ._helpers import mermaid_block


def render_sankey(result: MergeResult) -> str:
    lines = build_sankey_lines(result)
    return f"## Alignment Flow\n\n{mermaid_block(lines)}"
