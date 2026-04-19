#!/usr/bin/env python3
"""Reproduce production alignment scores and output per-component traces.

Usage example:
  python tools/prod_match_trace.py --channel morbid \
    --ref "The Horrific Murder of Jack Tupper- Part 2" --top 10
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import timezone
from typing import Any

from dateutil import parser as date_parser

from src.web.rss import RssEpisode
import src.catalog as catalog


def _parse_pub_date(raw: Any):
    if raw is None:
        return None
    try:
        dt = date_parser.parse(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _make_episode(d: dict[str, Any]) -> RssEpisode:
    return RssEpisode(
        id=str(d.get("id", "")),
        title=str(d.get("title", "")),
        author=str(d.get("author", "")) if d.get("author") is not None else "",
        content=str(d.get("content", "")) if d.get("content") is not None else "",
        description=d.get("description", ""),
        duration=d.get("duration"),
        pub_date=_parse_pub_date(d.get("pub_date")),
        image=d.get("image"),
    )


def _slugify(s: str) -> str:
    s = re.sub(r"\s+", "_", s.strip())
    s = re.sub(r"[^0-9a-zA-Z_]+", "_", s)
    return s.lower().strip("_")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--channel", required=True)
    p.add_argument("--ref", required=True, help="Reference title (substring allowed)")
    p.add_argument("--top", type=int, default=10)
    args = p.parse_args()

    path = os.path.join("downloads", args.channel, "feeds", "combined.json")
    if not os.path.exists(path):
        print("combined.json not found:", path)
        return 2

    with open(path, "r", encoding="utf8") as fh:
        data = json.load(fh)

    show = data.get("config", {}).get("name") or args.channel
    refs_raw = data.get("references", [])
    dls_raw = data.get("downloads", [])

    references = [_make_episode(d) for d in refs_raw]
    downloads = [_make_episode(d) for d in dls_raw]

    ref_candidates = catalog._build_alignment_candidates(references, show)
    dl_candidates = catalog._build_alignment_candidates(downloads, show)

    search = args.ref.lower().strip()
    ref_idx = None
    for i, r in enumerate(references):
        t = (r.title or "").lower().strip()
        if t == search or search in t:
            ref_idx = i
            break

    if ref_idx is None:
        print("Reference not found. Example titles (first 50):")
        for i, r in enumerate(references[:50]):
            print(f"{i+1}. {r.title}")
        return 3

    # Compute full production scores (matrix) for lookup
    prod_scores = catalog._build_alignment_scores(references, downloads, show)

    rows: list[dict[str, Any]] = []
    for d_idx, dl in enumerate(dl_candidates):
        s_title = catalog._similarity_clean(ref_candidates[ref_idx].title, dl.title)
        s_desc = catalog._similarity_clean(ref_candidates[ref_idx].description, dl.description)
        s_date = catalog.sim_date(ref_candidates[ref_idx].episode.pub_date, dl.episode.pub_date)
        s_id = catalog._id_similarity(ref_candidates[ref_idx].episode, dl.episode)
        computed = catalog._weighted_score(ref_candidates[ref_idx], dl, s_title, s_desc)
        prod = prod_scores.get((ref_idx, d_idx))
        rows.append(
            {
                "d_idx": d_idx,
                "id": dl.episode.id,
                "title": dl.episode.title,
                "s_title": s_title,
                "s_desc": s_desc,
                "s_date": s_date,
                "s_id": s_id,
                "computed": computed,
                "prod": prod,
            }
        )

    rows_sorted = sorted(rows, key=lambda r: r["computed"], reverse=True)
    top = rows_sorted[: args.top]

    print("Reference:", references[ref_idx].title)
    print(f"Show: {show}\nTop {args.top} candidates:")
    print(
        "| idx | id | title | title_sim | desc_sim | date_sim | id_sim | computed | prod | reason |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in top:
        reason = (
            "accepted"
            if (r["prod"] is not None and r["prod"] >= catalog.MATCH_TOLERANCE)
            else ("below_threshold" if r["prod"] is not None else "n/a")
        )
        print(
            f"| {r['d_idx']} | {r['id']} | {r['title']} | {r['s_title']:.3f} | {r['s_desc']:.3f} | {r['s_date']:.3f} | {int(r['s_id'])} | {r['computed']:.3f} | {r['prod'] if r['prod'] is not None else 'None'} | {reason} |"
        )

    out_fname = os.path.join(
        "downloads",
        args.channel,
        "feeds",
        f"trace_{_slugify(references[ref_idx].title)}.md",
    )
    with open(out_fname, "w", encoding="utf8") as out:
        out.write(f"# Trace for reference: {references[ref_idx].title}\n\n")
        out.write(f"Show: {show}\n\n")
        out.write(
            "| idx | id | title | title_sim | desc_sim | date_sim | id_sim | computed | prod | reason |\n"
        )
        out.write("|---|---|---|---|---|---|---|---|---|---|\n")
        for r in rows_sorted:
            reason = (
                "accepted"
                if (r["prod"] is not None and r["prod"] >= catalog.MATCH_TOLERANCE)
                else ("below_threshold" if r["prod"] is not None else "n/a")
            )
            out.write(
                f"| {r['d_idx']} | {r['id']} | {r['title']} | {r['s_title']:.3f} | {r['s_desc']:.3f} | {r['s_date']:.3f} | {int(r['s_id'])} | {r['computed']:.3f} | {r['prod'] if r['prod'] is not None else 'None'} | {reason} |\n"
            )

    print("\nWrote", out_fname)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
