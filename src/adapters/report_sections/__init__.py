from src.ports.report import ReportSection

from .duration_histogram import render_duration_histogram
from .filter_summary import render_filter_summary
from .match_rate import render_match_rate
from .monthly_volume import render_monthly_volume
from .overview import render_overview
from .sankey import render_sankey

DEFAULT_SECTIONS: list[ReportSection] = [
    render_overview,
    render_match_rate,
    render_monthly_volume,
    render_duration_histogram,
    render_filter_summary,
    render_sankey,
]

__all__ = ["DEFAULT_SECTIONS"]
