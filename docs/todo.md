# TODO

- [ ] Add a small machine-readable complexity resolution log entry, as described in `docs/COMPLEXITY.md`, before revising the complexity documentation itself.

## Diagnostics: match candidate helper

A small diagnostic helper `tools/match_diag.py` is included to let analysts inspect the top-N match candidates for a given reference title in a channel's `combined.json` without changing merge code.

Usage example:

```bash
# from the repo root
python tools/match_diag.py --channel morbid --ref "The Horrific Murder of Jack Tupper- Part 2" --top 5
```

What it shows:

- Normalized reference title
- Top-N download candidates with a simple score breakdown (title/description/date) and date-difference

Location:

- Script: `tools/match_diag.py`
- Input data: `downloads/<channel>/feeds/combined.json`

Additions to workflow:

- Run the diagnostic script for any unmatched reference to get quick insight into why the best candidate fell below `MATCH_TOLERANCE` (e.g., title variance, date mismatch, missing description).
