from src.ports import ReportDocument, ReportSection

from .duration_histogram import render_duration_histogram
from .filter_summary import render_filter_summary
from .match_debug import render_greedy_matches, render_matches
from .match_rate import render_match_rate
from .monthly_volume import render_monthly_volume
from .overview import render_overview
from .sankey import render_sankey

DEFAULT_REPORT_SECTIONS: list[ReportSection] = [
    render_overview,
    render_match_rate,
    render_monthly_volume,
    render_duration_histogram,
    render_filter_summary,
    render_sankey,
]

MATCH_SECTIONS: list[ReportSection] = [render_matches]

GREEDY_MATCH_SECTIONS: list[ReportSection] = [render_greedy_matches]

DEFAULT_DOCUMENTS: tuple[ReportDocument, ...] = (
    ReportDocument("report.md", tuple(DEFAULT_REPORT_SECTIONS)),
    ReportDocument("matches.md", tuple(MATCH_SECTIONS)),
    ReportDocument("greedy_matches.md", tuple(GREEDY_MATCH_SECTIONS)),
)

__all__ = [
    "DEFAULT_DOCUMENTS",
    "DEFAULT_REPORT_SECTIONS",
    "GREEDY_MATCH_SECTIONS",
    "MATCH_SECTIONS",
]
