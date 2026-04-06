#!/usr/bin/env python
"""Generate the Mermaid module dependency map for ARCHITECTURE_PLAYBOOK.md.

Uses grimp to build the import graph and networkx for hub analysis.

Usage:
    python runbook/analysis/build_diagram.py            # write to playbook
    python runbook/analysis/build_diagram.py --print    # print to stdout only
    python runbook/analysis/build_diagram.py --check    # exit 1 if playbook is stale
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import grimp
import networkx as nx

# ── Paths ─────────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).parent.parent.parent.resolve()
_PLAYBOOK = _ROOT / "docs" / "ARCHITECTURE_PLAYBOOK.md"
_PACKAGE = "src"

_SECTION_HEADING = "## Module Dependency Map"


# ── Layer classification ───────────────────────────────────────────────────────

_LAYER_ENTRY = "Entry Points"
_LAYER_APP = "App Layer"
_LAYER_FEATURES = "Features"
_LAYER_INFRA = "Infrastructure"
_LAYER_ORDER = [_LAYER_ENTRY, _LAYER_APP, _LAYER_FEATURES, _LAYER_INFRA]

_APP_MODULES = {"app_common", "app_runner"}
_FEATURE_DIRS = {"web", "youtube"}
_INFRA_DIRS = {"files", "utils", "models"}


def _classify(module_key: str) -> tuple[str, str | None]:
    top = module_key.split("/")[0]
    if top == "catalog":
        return _LAYER_ENTRY, None
    if top in _APP_MODULES:
        return _LAYER_APP, None
    if top in _FEATURE_DIRS:
        return _LAYER_FEATURES, top + "/"
    if top in _INFRA_DIRS:
        return _LAYER_INFRA, top + "/"
    return "Uncategorised", None


# ── Node helpers ───────────────────────────────────────────────────────────────


def _to_key(grimp_name: str) -> str:
    """'src.web.rss' → 'web/rss'."""
    return grimp_name.removeprefix(f"{_PACKAGE}.").replace(".", "/")


def _node_id(key: str) -> str:
    return key.replace("/", "_")


def _node_label(key: str) -> str:
    return Path(key).name + ".py"


# ── Graph building (grimp + networkx) ─────────────────────────────────────────


def _is_leaf(mod: str) -> bool:
    return "." in mod.removeprefix(_PACKAGE + ".") and mod != _PACKAGE


def _add_edges(G: nx.DiGraph, g: grimp.Graph, mod: str, key: str) -> None:
    for dep in g.find_modules_directly_imported_by(mod):
        dep_key = _to_key(dep)
        if dep_key != key and dep != _PACKAGE:
            G.add_edge(key, dep_key)


def _build_graph() -> nx.DiGraph:
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    g = grimp.build_graph(_PACKAGE, include_external_packages=False)
    G: nx.DiGraph = nx.DiGraph()
    for mod in sorted(m for m in g.modules if _is_leaf(m)):
        key = _to_key(mod)
        G.add_node(key)
        _add_edges(G, g, mod, key)
    return G


# ── Mermaid rendering ──────────────────────────────────────────────────────────


def _group_nodes(G: nx.DiGraph) -> tuple[dict, dict]:
    layer_groups: dict[str, list[str]] = {layer: [] for layer in _LAYER_ORDER}
    layer_groups["Uncategorised"] = []
    node_subgraph: dict[str, str] = {}
    for key in sorted(G.nodes):
        layer, subgraph = _classify(key)
        layer_groups.setdefault(layer, []).append(key)
        node_subgraph[key] = subgraph or ""
    return layer_groups, node_subgraph


def _render_sub_group(lines: list[str], sub_label: str, sub_keys: list[str]) -> None:
    if sub_label:
        safe_sub = "sg_" + sub_label.rstrip("/")
        lines.append(f'        subgraph {safe_sub}["{sub_label}"]')
        for key in sorted(sub_keys):
            lines.append(f'            {_node_id(key)}["{_node_label(key)}"]')
        lines.append("        end")
    else:
        for key in sorted(sub_keys):
            lines.append(f'        {_node_id(key)}["{_node_label(key)}"]')


def _render_subgraph(layer: str, keys: list[str], node_subgraph: dict) -> list[str]:
    if not keys:
        return []
    safe = "sg_" + layer.lower().replace(" ", "_")
    lines = [f'    subgraph {safe}["{layer}"]']
    sub_groups: dict[str, list[str]] = defaultdict(list)
    for key in sorted(keys):
        sub_groups[node_subgraph.get(key, "")].append(key)
    for sub_label, sub_keys in sorted(sub_groups.items()):
        _render_sub_group(lines, sub_label, sub_keys)
    lines.append("    end")
    return lines


def _render_insights(G: nx.DiGraph) -> list[str]:
    hubs = sorted([(n, d) for n, d in G.in_degree() if d >= 2], key=lambda x: -x[1])
    lines = ["", "### What this tells us", ""]
    if not hubs:
        lines.append("No significant hubs detected.")
        return lines
    lines += [
        "Nodes sorted by number of direct dependents (in-degree >= 2):",
        "",
        "| Module | Dependents |",
        "| --- | --- |",
        *[f"| `{k}.py` | {d} |" for k, d in hubs],
        "",
        "High in-degree modules have wide blast radius.",
        "Prioritise their stability and consider splitting if they also"
        " score high on Lizard.",
    ]
    return lines


def build_mermaid() -> str:
    G = _build_graph()
    layer_groups, node_subgraph = _group_nodes(G)

    lines = ["```mermaid", "graph TD"]
    for layer in _LAYER_ORDER + ["Uncategorised"]:
        lines.extend(
            _render_subgraph(layer, layer_groups.get(layer, []), node_subgraph)
        )
    lines.append("")
    for src_key, dep_key in sorted(G.edges()):
        lines.append(f"    {_node_id(src_key)} --> {_node_id(dep_key)}")
    lines.append("```")
    lines.extend(_render_insights(G))
    return "\n".join(lines)


# ── Playbook patch ─────────────────────────────────────────────────────────────

_INTRO = (
    "Edges represent real `from src.X import …` relationships in the source tree.\n"
    "Nodes are grouped into four layers ordered by dependency depth.\n"
    'Arrows point from dependent to dependency (read: "needs").\n'
    "This diagram is generated by `runbook/analysis/build_diagram.py`"
    " — do not edit by hand."
)


def _section_body(mermaid: str) -> str:
    return f"{_SECTION_HEADING}\n\n{_INTRO}\n\n{mermaid}\n"


def _patch_playbook(playbook: Path, new_section: str) -> bool:
    text = playbook.read_text(encoding="utf-8")
    start = text.find(_SECTION_HEADING)
    if start == -1:
        raise ValueError(f"{_SECTION_HEADING!r} not found in {playbook}")
    next_h2 = text.find("\n## ", start + len(_SECTION_HEADING))
    end = next_h2 + 1 if next_h2 != -1 else len(text)
    new_text = text[:start] + new_section + "\n" + text[end:]
    if new_text == text:
        return False
    playbook.write_text(new_text, encoding="utf-8")
    return True


# ── CLI ────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Mermaid module dependency diagram"
    )
    parser.add_argument("--print", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--playbook", default=str(_PLAYBOOK))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    playbook = Path(args.playbook)
    mermaid = build_mermaid()
    section = _section_body(mermaid)

    if args.print:
        print(section)
        return 0

    if args.check:
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp:
            shutil.copy(playbook, tmp.name)
            changed = _patch_playbook(Path(tmp.name), section)
        if changed:
            print("diagram: playbook diagram is stale — run build_diagram.py")
            return 1
        print("diagram: playbook diagram is up to date")
        return 0

    changed = _patch_playbook(playbook, section)
    status = "updated" if changed else "already up to date"
    print(f"diagram: {status} {playbook.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
