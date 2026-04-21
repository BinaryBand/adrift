from src.models import MergeResult

from ._helpers import mermaid_block

_BUCKETS: list[tuple[str, float, float]] = [
    ("<10m", 0, 600),
    ("10-30m", 600, 1800),
    ("30-60m", 1800, 3600),
    ("60-90m", 3600, 5400),
    ("90m+", 5400, float("inf")),
]
_BUCKET_LABELS = [b[0] for b in _BUCKETS]


def _extract_durations(result: MergeResult) -> list[float]:
    return [ep.duration for ep in (result.references or []) if ep.duration is not None]


def _bucket_counts(durations: list[float]) -> list[int]:
    return [sum(1 for d in durations if lo <= d < hi) for _, lo, hi in _BUCKETS]


def render_duration_histogram(result: MergeResult) -> str:
    durations = _extract_durations(result)
    if not durations:
        return ""
    counts = _bucket_counts(durations)
    labels = '", "'.join(_BUCKET_LABELS)
    values = ", ".join(map(str, counts))
    y_max = max(counts) or 1
    lines = [
        "xychart-beta",
        '    title "Episode Duration Distribution"',
        f'    x-axis ["{labels}"]',
        f'    y-axis "Episodes" 0 --> {y_max}',
        f"    bar [{values}]",
    ]
    return f"## Duration Distribution\n\n{mermaid_block(lines)}"
