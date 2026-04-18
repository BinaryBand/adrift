from src.models.pipeline import MergeResult

from ._helpers import mermaid_block


def _match_counts(result: MergeResult) -> tuple[int, int, int]:
    return (
        len(result.references or []),
        len(result.downloads or []),
        len(result.pairs or []),
    )


def render_match_rate(result: MergeResult) -> str:
    ref_count, dl_count, matched = _match_counts(result)
    if not ref_count and not dl_count:
        return ""
    unmatched_ref = max(ref_count - matched, 0)
    unmatched_dl = max(dl_count - matched, 0)
    y_max = max(ref_count, dl_count, 1)
    lines = [
        "xychart-beta",
        '    title "Episode Match Breakdown"',
        '    x-axis ["Matched Refs", "Unmatched Refs", "Matched Downloads", "Unmatched Downloads"]',
        f'    y-axis "Episodes" 0 --> {y_max}',
        f"    bar [{matched}, {unmatched_ref}, {matched}, {unmatched_dl}]",
    ]
    return f"## Match Rate\n\n{mermaid_block(lines)}"
