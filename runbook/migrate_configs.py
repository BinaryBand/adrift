#!/usr/bin/env python3
"""Migrate JSON config files in `config/` to TOML (`config/*.toml`).

For each JSON file (including dotfiles) this script will:
- load the JSON array of podcast entries
- load the corresponding TOML (if present) and detect existing titles
- append missing entries as [[podcasts]] blocks to the TOML file
- back up the original JSON to `<name>.json.bak` and remove the JSON file

Run without args to operate on all JSON files in `config/`.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
import shutil
import sys
import argparse


def convert_schedule(val):
    if val is None:
        return None
    if isinstance(val, list):
        if len(val) == 1 and str(val[0]).lower() == "weekly":
            return "FREQ=WEEKLY"
        mapping = {
            "mon": "MO",
            "tue": "TU",
            "wed": "WE",
            "thu": "TH",
            "fri": "FR",
            "sat": "SA",
            "sun": "SU",
        }
        days = [mapping.get(str(d).lower(), str(d).upper()) for d in val]
        return "FREQ=WEEKLY;BYDAY=" + ",".join(days)
    if isinstance(val, str):
        if val.lower() == "weekly":
            return "FREQ=WEEKLY"
        parts = [p.strip() for p in val.split(",") if p.strip()]
        return convert_schedule(parts)
    return None


def toml_block_for_entry(entry: dict) -> str:
    # Build a TOML block string for a single podcasts entry.
    lines: list[str] = []
    lines.append("\n[[podcasts]]")

    def jd(v):
        return json.dumps(v, ensure_ascii=False)

    # Core fields
    if "title" in entry:
        lines.append(f"title = {jd(entry['title'])}")
    if "path" in entry:
        lines.append(f"path = {jd(entry['path'])}")
    if "feeds" in entry and entry["feeds"] is not None:
        lines.append(f"feeds = {jd(entry['feeds'])}")
    if "sources" in entry and entry["sources"] is not None:
        lines.append(f"sources = {jd(entry['sources'])}")

    # Schedule
    sched = None
    if "download_schedule" in entry:
        sched = convert_schedule(entry.get("download_schedule"))
    elif "schedule" in entry:
        sched = entry.get("schedule")
    if sched:
        lines.append(f"schedule = {jd(sched)}")

    # Filters: map legacy keys to new nested tables
    if "filter" in entry and entry.get("filter"):
        lines.append("\n[podcasts.filters]")
        lines.append(f"include = {jd([entry.get('filter')])}")

    if "feed_filter" in entry and entry.get("feed_filter"):
        lines.append("\n[podcasts.feed_filters]")
        lines.append(f"include = {jd([entry.get('feed_filter')])}")

    if "source_filter" in entry and entry.get("source_filter"):
        lines.append("\n[podcasts.source_filters]")
        lines.append(f"include = {jd([entry.get('source_filter')])}")

    return "\n".join(lines) + "\n"


def migrate_json_file(
    json_path: Path, toml_path: Path, remove_json: bool = True
) -> tuple[int, int]:
    """Return (added, skipped) counts."""
    if not json_path.exists():
        return (0, 0)

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list) or len(data) == 0:
        print(f"No entries in {json_path}, skipping.")
        return (0, 0)

    existing_titles = set()
    if toml_path.exists():
        try:
            with toml_path.open("rb") as f:
                raw = tomllib.load(f)
                podcasts = raw.get("podcasts", [])
                for p in podcasts:
                    t = p.get("title")
                    if isinstance(t, str):
                        existing_titles.add(t)
        except Exception as e:
            print(f"Warning: failed to parse existing TOML {toml_path}: {e}")

    added = 0
    skipped = 0
    append_lines: list[str] = []

    for entry in data:
        title = entry.get("title")
        if not title:
            skipped += 1
            continue
        if title in existing_titles:
            skipped += 1
            continue

        append_lines.append(toml_block_for_entry(entry))
        added += 1

    if added > 0:
        toml_path.parent.mkdir(parents=True, exist_ok=True)
        with toml_path.open("a", encoding="utf-8") as f:
            f.write("\n# Appended by migrate_configs.py\n")
            for block in append_lines:
                f.write(block)

    # back up and optionally remove the original JSON
    bak = json_path.with_suffix(json_path.suffix + ".bak")
    shutil.copy2(json_path, bak)
    if remove_json:
        json_path.unlink()

    return (added, skipped)


def main():
    parser = argparse.ArgumentParser(description="Migrate JSON config files to TOML")
    parser.add_argument(
        "--no-remove-json",
        dest="remove",
        action="store_false",
        help="Do not remove original JSON files (they will still be backed up)",
    )
    args = parser.parse_args()

    cfg_dir = Path(__file__).parent.parent / "config"
    json_files = [p for p in cfg_dir.iterdir() if p.suffix == ".json"]

    if not json_files:
        print("No JSON config files found in config/; nothing to do.")
        return

    total_added = 0
    total_skipped = 0

    for jf in json_files:
        # Derive toml filename by stripping leading dot and changing suffix
        name = jf.name
        target_name = name.lstrip(".").rsplit(".", 1)[0] + ".toml"
        toml_path = cfg_dir / target_name
        print(f"Migrating {jf} -> {toml_path}")
        added, skipped = migrate_json_file(jf, toml_path, remove_json=args.remove)
        print(f"  added={added}, skipped={skipped}")
        total_added += added
        total_skipped += skipped

    print(f"Migration complete. added={total_added}, skipped={total_skipped}")


if __name__ == "__main__":
    main()
