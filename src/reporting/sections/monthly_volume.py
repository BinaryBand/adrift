from collections import Counter
from datetime import datetime, timezone

from src.models import EpisodeData, MergeResult

from ._helpers import mermaid_block


def _last_12_months(now: datetime) -> list[str]:
    months: list[str] = []
    year, month = now.year, now.month
    for _ in range(12):
        months.append(f"{year}-{month:02d}")
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(months))


def _ep_months_in_window(episodes: list[EpisodeData], month_set: set[str]) -> list[str]:
    result: list[str] = []
    for ep in episodes:
        if ep.upload_date is None:
            continue
        m = ep.upload_date.strftime("%Y-%m")
        if m in month_set:
            result.append(m)
    return result


def render_monthly_volume(result: MergeResult) -> str:
    months = _last_12_months(datetime.now(timezone.utc))
    ep_months = _ep_months_in_window(result.episodes or [], set(months))
    if not ep_months:
        return ""
    counts: Counter[str] = Counter(ep_months)
    month_counts = [counts.get(m, 0) for m in months]
    values = ", ".join(map(str, month_counts))
    y_max = max(month_counts) or 1
    x_labels = '", "'.join(months)
    lines = [
        "xychart-beta",
        '    title "Monthly Episode Volume (last 12 months)"',
        f'    x-axis ["{x_labels}"]',
        f'    y-axis "Episodes" 0 --> {y_max}',
        f"    bar [{values}]",
    ]
    return f"## Monthly Episode Volume\n\n{mermaid_block(lines)}"
