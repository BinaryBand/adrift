# Re-export all report section renderers
from src.reporting.sections._helpers import md_table, mermaid_block, pct
from src.reporting.sections.duration_histogram import render_duration_histogram
from src.reporting.sections.filter_summary import render_filter_summary
from src.reporting.sections.match_debug import (
    render_greedy_matches,
    render_match_debug,
    render_matches,
)
from src.reporting.sections.match_rate import render_match_rate
from src.reporting.sections.monthly_volume import render_monthly_volume
from src.reporting.sections.overview import render_overview
from src.reporting.sections.sankey import render_sankey

__all__ = [
    "mermaid_block",
    "md_table",
    "pct",
    "render_duration_histogram",
    "render_filter_summary",
    "render_greedy_matches",
    "render_matches",
    "render_match_debug",
    "render_match_rate",
    "render_monthly_volume",
    "render_overview",
    "render_sankey",
]
