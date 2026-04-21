from src.models import MergeResult, SourceTrace

from ._helpers import md_table


def _filter_description(trace: SourceTrace) -> str:
    f = trace.filters
    parts: list[str] = []
    if f.include:
        parts.append(f"include: {', '.join(f.include)}")
    if f.exclude:
        parts.append(f"exclude: {', '.join(f.exclude)}")
    if f.r_rules:
        parts.append(f"rrule: {len(f.r_rules)} rule(s)")
    return "  ".join(parts)


def _filtered_traces(result: MergeResult) -> list[SourceTrace]:
    return [t for t in (result.source_traces or []) if t.has_filters]


def _trace_row(t: SourceTrace) -> list[str]:
    url = t.url[:57] + "" if len(t.url) > 60 else t.url
    return [t.role, t.source_type, url, str(t.episode_count), _filter_description(t)]


def render_filter_summary(result: MergeResult) -> str:
    filtered = _filtered_traces(result)
    if not filtered:
        return ""
    rows = [_trace_row(t) for t in filtered]
    table = md_table(["Role", "Type", "Source", "Episodes", "Active Filters"], rows)
    return f"## Active Filters\n\n{table}"
