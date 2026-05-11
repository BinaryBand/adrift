#!/usr/bin/env python
"""Generate a churn+complexity hotspot map for PLAYBOOK.md.

Usage:
    python runbook/analysis/build_hotspots.py            # write to playbook
    python runbook/analysis/build_hotspots.py --print    # print to stdout only
    python runbook/analysis/build_hotspots.py --check    # exit 1 if playbook is stale
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

import lizard

_ROOT = Path(__file__).parent.parent.parent.resolve()
_PLAYBOOK = _ROOT / "docs" / "PLAYBOOK.md"
_SRC = _ROOT / "src"

_SECTION_HEADING = "## Refactoring Hotspot Map"
_INSERT_BEFORE_HEADING = "## Use this process when"


def _rel_to_root(path: Path) -> str:
    return path.resolve().relative_to(_ROOT).as_posix()


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _complexity_by_file(paths: list[Path]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for path in paths:
        analysis = cast(Any, lizard.analyze_file(str(path)))
        totals[_rel_to_root(path)] = int(analysis.CCN)
    return totals


def _churn_by_file(days: int) -> dict[str, int]:
    cmd = [
        "git",
        "log",
        f"--since={days}.days",
        "--name-only",
        "--pretty=format:",
        "--",
        "src",
    ]
    result = subprocess.run(cmd, cwd=_ROOT, check=True, text=True, capture_output=True)

    counts: dict[str, int] = {}
    for raw in result.stdout.splitlines():
        name = raw.strip()
        if not name or not name.endswith(".py"):
            continue
        counts[name] = counts.get(name, 0) + 1
    return counts


def _normalise(values: dict[str, int]) -> dict[str, float]:
    if not values:
        return {}
    max_value = max(values.values())
    if max_value == 0:
        return {k: 0.0 for k in values}
    return {k: v / max_value for k, v in values.items()}


def _quadrant(churn_n: float, ccn_n: float) -> str:
    bits = ("H" if churn_n >= 0.6 else "L") + ("H" if ccn_n >= 0.6 else "L")
    return bits


def _node_id(path: str) -> str:
    return path.replace("/", "_").replace(".", "_")


def _node_label(path: str, churn: int, ccn: int, score: float) -> str:
    short = path.removeprefix("src/")
    return f"{short}\\nchurn={churn} ccn={ccn} score={score:.2f}"


def _row_for_path(
    path: str,
    metrics: dict[str, dict[str, int] | dict[str, float]],
) -> dict[str, object]:
    ccn = metrics["ccn"]
    churn = metrics["churn"]
    ccn_n = metrics["ccn_n"]
    churn_n = metrics["churn_n"]

    ccn_value = ccn.get(path, 0)
    churn_value = churn.get(path, 0)
    ccn_norm = ccn_n.get(path, 0.0)
    churn_norm = churn_n.get(path, 0.0)
    score = ccn_norm * churn_norm
    return {
        "path": path,
        "ccn": ccn_value,
        "churn": churn_value,
        "ccn_n": ccn_norm,
        "churn_n": churn_norm,
        "score": score,
        "quadrant": _quadrant(churn_norm, ccn_norm),
    }


def _sort_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(rows, key=lambda r: (r["score"], r["ccn"], r["churn"]), reverse=True)


def _build_rows(days: int) -> list[dict[str, object]]:
    files = _iter_python_files(_SRC)
    ccn = _complexity_by_file(files)
    churn = _churn_by_file(days)

    ccn_n = _normalise(ccn)
    churn_n = _normalise(churn)
    metrics: dict[str, dict[str, int] | dict[str, float]] = {
        "ccn": ccn,
        "churn": churn,
        "ccn_n": ccn_n,
        "churn_n": churn_n,
    }

    merged = sorted(set(ccn) | set(churn))
    rows = [_row_for_path(path, metrics) for path in merged]
    return _sort_rows(rows)


def _group_quadrants(
    top_rows: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    groups: dict[str, list[dict[str, object]]] = {
        "HH": [],
        "HL": [],
        "LH": [],
        "LL": [],
    }
    for row in top_rows:
        groups[str(row["quadrant"])].append(row)
    return groups


def _append_quadrant(
    lines: list[str],
    groups: dict[str, list[dict[str, object]]],
    key: str,
    label: str,
) -> None:
    lines.append(f'    subgraph sg_{key.lower()}["{label}"]')
    for row in groups[key]:
        node = _node_id(str(row["path"]))
        node_label = _node_label(
            str(row["path"]),
            int(cast(int, row["churn"])),
            int(cast(int, row["ccn"])),
            float(cast(float, row["score"])),
        )
        lines.append(f'        {node}["{node_label}"]')
    lines.append("    end")


def _render_mermaid(rows: list[dict[str, object]], top_n: int) -> str:
    groups = _group_quadrants(rows[:top_n])
    lines = ["```mermaid", "graph TD"]
    _append_quadrant(lines, groups, "HH", "High churn / High complexity")
    _append_quadrant(lines, groups, "HL", "High churn / Lower complexity")
    _append_quadrant(lines, groups, "LH", "Lower churn / High complexity")
    _append_quadrant(lines, groups, "LL", "Lower churn / Lower complexity")

    lines.append("```")
    return "\n".join(lines)


def _render_table(rows: list[dict[str, object]], top_n: int) -> str:
    lines = [
        "| File | Churn (last window) | Total CCN | Score |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows[:top_n]:
        path_display = row["path"]
        churn_val = int(cast(int, row["churn"]))
        ccn_val = int(cast(int, row["ccn"]))
        score_val = float(cast(float, row["score"]))
        lines.append(f"| `{path_display}` | {churn_val} | {ccn_val} | {score_val:.2f} |")
    return "\n".join(lines)


def _section_body(days: int, top_n: int, rows: list[dict[str, object]]) -> str:
    mermaid = _render_mermaid(rows, top_n)
    table = _render_table(rows, top_n)
    intro = (
        "This map combines git churn and Lizard total CCN to rank refactoring targets.\n"
        "\n"
        "- Churn window: last "
        f"{days} days\n"
        f"- Hotspot score: normalised_churn * normalised_ccn\n"
        "\n"
        "Generated by `runbook/analysis/build_hotspots.py` — do not edit by hand."
    )
    return f"{_SECTION_HEADING}\n\n{intro}\n\n{mermaid}\n\n### Top Hotspots\n\n{table}\n"


def _replace_existing_section(text: str, section: str) -> tuple[str, bool]:
    start = text.find(_SECTION_HEADING)
    if start == -1:
        return text, False
    next_h2 = text.find("\n## ", start + len(_SECTION_HEADING))
    end = next_h2 + 1 if next_h2 != -1 else len(text)
    return text[:start] + section + "\n" + text[end:], True


def _insert_new_section(text: str, section: str) -> str:
    marker = text.find(_INSERT_BEFORE_HEADING)
    if marker == -1:
        return text.rstrip() + "\n\n" + section + "\n"
    return text[:marker] + section + "\n" + text[marker:]


def _patch_playbook(playbook: Path, new_section: str) -> bool:
    text = playbook.read_text(encoding="utf-8")
    replaced_text, found = _replace_existing_section(text, new_section)
    new_text = replaced_text if found else _insert_new_section(text, new_section)
    if new_text == text:
        return False
    playbook.write_text(new_text, encoding="utf-8")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate churn+complexity hotspot map")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--print", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--playbook", default=str(_PLAYBOOK))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = _build_rows(args.days)
    section = _section_body(args.days, args.top, rows)

    if args.print:
        print(section)
        return 0

    playbook = Path(args.playbook)

    if args.check:
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp:
            shutil.copy(playbook, tmp.name)
            changed = _patch_playbook(Path(tmp.name), section)
        if changed:
            print("hotspots: playbook hotspot map is stale — run build_hotspots.py")
            return 1
        print("hotspots: playbook hotspot map is up to date")
        return 0

    changed = _patch_playbook(playbook, section)
    status = "updated" if changed else "already up to date"
    print(f"hotspots: {status} {playbook.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
