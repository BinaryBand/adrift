from pathlib import Path

from src.models.pipeline import MergeResult
from src.ports.mermaid import MermaidRenderOptions


def _sanitize_label(s: str | None, max_len: int = 60) -> str:
    if s is None:
        s = ""
    s = s.replace("\n", " ").replace("\r", " ")
    s = " ".join(s.split())
    s = s.replace('"', '\\"').replace("]", "")
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def _sanitize_sankey_node(s: str, max_len: int = 60) -> str:
    value = _sanitize_label(s, max_len=max_len)
    return value.replace(",", "").replace(":", " ")


def _append_sankey_row(lines: list[str], source: str, target: str, value: int) -> None:
    if value <= 0:
        return
    lines.append(f"    {source},{target},{value}")


def _role_traces(result: MergeResult, role: str):
    return [trace for trace in (result.source_traces or []) if trace.role == role]


def _trace_episode_count(result: MergeResult, role: str, has_filters: bool) -> int:
    traces = [trace for trace in _role_traces(result, role) if trace.has_filters is has_filters]
    return sum(trace.episode_count for trace in traces)


def _group_counts(result: MergeResult) -> dict[str, int]:
    reference_count = len(result.references or [])
    download_count = len(result.downloads or [])
    matched_count = len(result.pairs or [])
    merged_count = len(result.episodes or [])
    return {
        "reference_count": reference_count,
        "download_count": download_count,
        "matched_reference_count": matched_count,
        "matched_download_count": matched_count,
        "unmatched_reference_count": max(reference_count - matched_count, 0),
        "unmatched_download_count": max(download_count - matched_count, 0),
        "merged_count": merged_count,
    }


def build_sankey_lines(result: MergeResult) -> list[str]:
    counts = _group_counts(result)
    title = _sanitize_sankey_node(result.config.name, max_len=80)
    lines = ["sankey-beta"]
    labels = _sankey_labels(counts, title)
    _append_filter_stage_rows(lines, result, labels)
    _append_match_stage_rows(lines, counts, labels)
    return lines


def _sankey_labels(counts: dict[str, int], title: str) -> dict[str, str]:
    return {
        "references": f"Reference Episodes ({counts['reference_count']})",
        "matched_refs": f"Matched References ({counts['matched_reference_count']})",
        "unmatched_refs": f"Unmatched References ({counts['unmatched_reference_count']})",
        "downloads": f"Download Episodes ({counts['download_count']})",
        "matched_downloads": f"Matched Downloads ({counts['matched_download_count']})",
        "unmatched_downloads": (f"Unmatched Downloads ({counts['unmatched_download_count']})"),
        "merged": f"Merged Episodes for {title} ({counts['merged_count']})",
    }


def _append_filter_stage_rows(
    lines: list[str],
    result: MergeResult,
    labels: dict[str, str],
) -> None:
    if not result.source_traces:
        return
    _append_role_filter_stage(lines, result, "reference", labels["references"])
    _append_role_filter_stage(lines, result, "download", labels["downloads"])


def _append_role_filter_stage(
    lines: list[str],
    result: MergeResult,
    role: str,
    final_label: str,
) -> None:
    filtered_episodes = _trace_episode_count(result, role, True)
    plain_episodes = _trace_episode_count(result, role, False)
    source_episodes = _source_episode_label(role, filtered_episodes + plain_episodes)
    filtered_label = _filtered_episode_label(role, filtered_episodes)
    plain_label = _unfiltered_episode_label(role, plain_episodes)
    _append_sankey_row(lines, source_episodes, filtered_label, filtered_episodes)
    _append_sankey_row(lines, source_episodes, plain_label, plain_episodes)
    _append_sankey_row(lines, filtered_label, final_label, filtered_episodes)
    _append_sankey_row(lines, plain_label, final_label, plain_episodes)


def _source_episode_label(role: str, count: int) -> str:
    prefix = "Reference" if role == "reference" else "Download"
    return f"{prefix} Source Episodes ({count})"


def _filtered_episode_label(role: str, count: int) -> str:
    prefix = "Reference" if role == "reference" else "Download"
    return f"{prefix} Episodes from Filtered Sources ({count})"


def _unfiltered_episode_label(role: str, count: int) -> str:
    prefix = "Reference" if role == "reference" else "Download"
    return f"{prefix} Episodes from Unfiltered Sources ({count})"


def _append_match_stage_rows(
    lines: list[str],
    counts: dict[str, int],
    labels: dict[str, str],
) -> None:
    rows = [
        ("references", "matched_refs", "matched_reference_count"),
        ("references", "unmatched_refs", "unmatched_reference_count"),
        ("downloads", "matched_downloads", "matched_download_count"),
        ("downloads", "unmatched_downloads", "unmatched_download_count"),
        ("matched_refs", "merged", "matched_reference_count"),
        ("matched_downloads", "merged", "matched_download_count"),
    ]
    for source_key, target_key, count_key in rows:
        _append_sankey_row(lines, labels[source_key], labels[target_key], counts[count_key])


def _build_flowchart_lines(result: MergeResult) -> list[str]:
    counts = _group_counts(result)
    title = _sanitize_label(result.config.name, max_len=80)
    return [
        "flowchart LR",
        *_reference_flowchart_lines(counts),
        *_download_flowchart_lines(counts),
        *_merged_flowchart_lines(counts, title),
    ]


def _reference_flowchart_lines(counts: dict[str, int]) -> list[str]:
    return [
        (
            f'  refs["Reference Episodes\n{counts["reference_count"]}"] '
            f"-->|matched {counts['matched_reference_count']}| "
            'matched_refs["Matched References"]'
        ),
        (
            f"  refs -->|unmatched {counts['unmatched_reference_count']}| "
            'unmatched_refs["Unmatched References"]'
        ),
    ]


def _download_flowchart_lines(counts: dict[str, int]) -> list[str]:
    return [
        (
            f'  downloads["Download Episodes\n{counts["download_count"]}"] '
            f"-->|matched {counts['matched_download_count']}| "
            'matched_downloads["Matched Downloads"]'
        ),
        (
            f"  downloads -->|unmatched {counts['unmatched_download_count']}| "
            'unmatched_downloads["Unmatched Downloads"]'
        ),
    ]


def _merged_flowchart_lines(counts: dict[str, int], title: str) -> list[str]:
    return [
        (
            f"  matched_refs -->|{counts['matched_reference_count']}| "
            f'merged["Merged Episodes\n{title}\n{counts["merged_count"]}"]'
        ),
        f"  matched_downloads -->|{counts['matched_download_count']}| merged",
    ]


def _coerce_render_options(
    options: MermaidRenderOptions | None,
) -> MermaidRenderOptions:
    return options or MermaidRenderOptions()


def _resolve_output_path(
    result: MergeResult,
    output_root: Path,
    options: MermaidRenderOptions,
) -> Path:
    filename = options.filename or "alignment_sankey.md"
    out_dir = output_root / result.config.slug / "feeds"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / filename


def _build_markdown(result: MergeResult, format_name: str) -> str:
    counts = _group_counts(result)
    lines = [
        f"# Alignment Summary: {result.config.name}",
        "",
        (
            "Matched "
            f"{counts['merged_count']} episodes from "
            f"{counts['reference_count']} references and "
            f"{counts['download_count']} downloads."
        ),
        "",
        "```mermaid",
    ]
    if format_name == "sankey":
        lines.extend(build_sankey_lines(result))
    else:
        lines.extend(_build_flowchart_lines(result))
    lines.append("```")
    return "\n".join(lines) + "\n"


class FileMermaidAdapter:
    """File-backed Mermaid adapter that writes a Markdown file with a Mermaid block."""

    def generate_diagrams(
        self,
        result: MergeResult,
        output_root: Path,
        options: MermaidRenderOptions | None = None,
    ) -> list[Path]:
        render_options = _coerce_render_options(options)
        output_root = Path(output_root)
        out_path = _resolve_output_path(result, output_root, render_options)

        if out_path.exists() and not render_options.overwrite:
            return [out_path]

        markdown = _build_markdown(result, render_options.format)
        out_path.write_text(markdown, encoding="utf-8")
        return [out_path]


__all__ = ["FileMermaidAdapter", "build_sankey_lines"]
