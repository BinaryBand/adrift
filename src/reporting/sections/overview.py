from src.models import MergeResult

from ._helpers import md_table, pct


def render_overview(result: MergeResult) -> str:
    ref_count = len(result.references or [])
    dl_count = len(result.downloads or [])
    matched = len(result.pairs or [])
    merged = len(result.episodes or [])
    rows = [
        ["References", str(ref_count), str(matched), pct(matched, ref_count)],
        ["Downloads", str(dl_count), str(matched), pct(matched, dl_count)],
        ["Merged output", str(merged), "", ""],
    ]
    table = md_table(["Role", "Total", "Matched", "Match Rate"], rows)
    return f"# {result.config.name}\n\n{table}"
