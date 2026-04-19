#!/usr/bin/env python3
"""Diagnostic: show top-N candidate breakdown for a reference title in a channel's combined.json.

This is a lightweight tool analysts can run locally without changing merge logic.

Usage:
  python tools/match_diag.py --channel morbid --ref "The Horrific Murder of Jack Tupper- Part 2" --top 5

It prints the top candidates with a simple breakdown mirroring the production weights.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from datetime import datetime
from rapidfuzz import fuzz


def normalize(text: str) -> str:
    if not text:
        return ""
    t = text.lower().strip()
    # normalize common part markers
    t = t.replace("(pt.", "part ")
    t = t.replace("(pt", "part ")
    t = t.replace("pt.", "part ")
    # replace roman numerals simple cases
    t = t.replace(" ii", " 2").replace(" iii", " 3").replace(" iv", " 4")
    t = t.replace("/", " ")
    # collapse whitespace
    return " ".join(t.split())


def parse_date(d):
    if not d:
        return None
    try:
        return datetime.fromisoformat(d.replace("Z", "+00:00"))
    except Exception:
        return None


def title_score(a, b):
    return fuzz.token_set_ratio(a, b) / 100.0


def desc_score(a, b):
    return fuzz.ratio((a or ""), (b or "")) / 100.0


def date_score(a, b):
    if not a or not b:
        return 0.0
    delta = abs((a - b).days)
    if delta <= 2:
        return 1.0
    if delta <= 10:
        return 0.7
    if delta <= 35:
        return 0.15
    return 0.0


def main():
    p = argparse.ArgumentParser(description="Show top-N match candidates for a reference title")
    p.add_argument("--channel", required=True, help="downloads/<channel>/feeds/combined.json")
    p.add_argument("--ref", required=True, help="Reference title (substring match is allowed)")
    p.add_argument("--top", type=int, default=5, help="Number of top candidates to show")
    args = p.parse_args()

    combined = Path(f"downloads/{args.channel}/feeds/combined.json")
    if not combined.exists():
        print("combined.json not found:", combined)
        return
    data = json.loads(combined.read_text(encoding="utf-8"))

    refs = data.get("references", [])
    # downloads may be in a different key depending on merged shape; try common alternatives
    dls = data.get("downloads") or data.get("entries") or data.get("downloads_entries") or data.get("downloads", []) or refs

    ref = None
    for r in refs:
        if args.ref.lower() in (r.get("title", "").lower()):
            ref = r
            break
    if not ref:
        print("Reference not found in combined.json")
        return

    ref_title = normalize(ref.get("title", ""))
    ref_desc = ref.get("description", "")
    ref_date = parse_date(ref.get("pub_date"))

    candidates = []
    for i, c in enumerate(dls):
        c_title_raw = c.get("title", "")
        c_title = normalize(c_title_raw)
        c_desc = c.get("description", "")
        c_date = parse_date(c.get("pub_date"))
        s_title = title_score(ref_title, c_title)
        s_desc = desc_score(ref_desc, c_desc)
        s_date = date_score(ref_date, c_date)
        # Mirror production weights: title 0.5, desc 0.1, date 0.3, id bonus ignored here
        total = 0.5 * s_title + 0.1 * s_desc + 0.3 * s_date
        candidates.append({
            "index": i,
            "title": c_title_raw,
            "norm_title": c_title,
            "total": total,
            "title_score": s_title,
            "desc_score": s_desc,
            "date_score": s_date,
            "pub_date": c.get("pub_date"),
        })

    candidates.sort(key=lambda x: x["total"], reverse=True)
    print(f"Reference: {ref.get('title')}")
    print(f"Normalized Reference Title: {ref_title}")
    print("Top candidates:")
    for rank, c in enumerate(candidates[: args.top], start=1):
        date_diff = None
        try:
            if ref_date and c.get("pub_date"):
                cd = parse_date(c.get("pub_date"))
                if cd:
                    date_diff = abs((ref_date - cd).days)
        except Exception:
            date_diff = None
        print(
            f"{rank}. idx={c['index']} | total={c['total']:.3f} | title={c['title_score']:.3f} | desc={c['desc_score']:.3f} | date={c['date_score']:.3f} | date_diff={date_diff} | {c['title']}"
        )


if __name__ == "__main__":
    main()
