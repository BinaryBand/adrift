# Morbid Alignment Mistakes

This file summarizes the Morbid alignment audit, the fixes applied during the
improvement sprint, remaining failure modes, and the tests that prevent
regressions.

Source data: `downloads/morbid/manual_matches_audit_detailed.csv`,
`downloads/morbid/feeds/combined.json` (`match_traces`),
`tests/resources/alignment/morbid_benchmark.csv` (regression rows).

---

## Snapshot (baseline: 340 matched)

Reviewed: 518 references.

- `likely_no_matching_download`: 180 — references with no download counterpart
- `problematic_series_mismatch`: 67 — wrong episode/series index (e.g. Listener Tales)
- `problematic_reused_target`: 20 — a generic download is repeatedly selected
- `problematic_misrank`: 13 — better lexical candidate exists but was not chosen
- `problematic_part_mismatch`: 2 — wrong part index in multi-part titles
- `likely_correct_variant`: 55 — acceptable variants
- `unclear`: 181 — require manual review

Examples (representative):

- Missing source: `ref 556` "Tara Calico" (best_score=0.249)
- Series mismatch: `ref 386` "Listener Tales 59" → "Listener Tales 109"
- Reused target: `download_index 242` selected by 13 refs
- Part mismatch: "Theodore Durrant Part 2" → Part 1

---

## Fixes applied (340 → 363)

Summary: three targeted normalisations and two scoring adjustments recovered 23
real matches.

- Brand-suffix stripping: removed common `| Morbid...` tails in
  `_clean_morbid_title` (5 specific patterns). (+3)
- Title-certainty shortcut: when normalized-title score ≥ 0.97, skip date and
  description signals (helps YouTube backfills). (+~3)
- Containment bonus: +0.08 when shorter title's anchor tokens (≥2) appear in the
  longer title (helps truncated RSS vs verbose YouTube titles). (+~3)
- Trailing `| Episode N` strip: remove `| Episode <num>` that remains after
  brand stripping (preserve `| Part N`). (+13)
- Upload-prefix stripping: drop leading `Fan Favorite:` and `Episode Revisit:`.
  (+~1 net)

Representative recovered cases: Bermondsey Horror (large date gap), Kelly
Cochran (episode number noise removed), Fan Favorite / Episode Revisit uploads.

---

## Remaining failures (concise)

- Greedy conflicts (2): high-score candidates lost to earlier refs; requires
  two-pass assignment or manual overrides.
- Structural mismatches (≈3): RSS and YouTube titles use different wording — need
  manual mapping or weaker thresholds per-case.
- Coverage gap (~475): many refs (2018–2021) have no YouTube download; this is a
  source-coverage problem, not a scoring bug.

Notes: ~22 near-misses remain in the 0.60–0.75 score band; raising the global
threshold risks false positives, so handle borderline cases individually.

---

## Tests & guards

- Regression rows: `tests/resources/alignment/morbid_benchmark.csv`. Add a row for
  every fixed case to prevent regressions.
- Unit guards: `tests/catalog/test_align_episodes.py` covers:
  - certainty-path/date-skip, containment bonus, listener-tales/part/volume
    guards, and anchor-overlap requirements.
- Lint/quality: `tests/test_lint.py` enforces ruff, import sort, and CCN ≤ 8.

---

## Recommended actions

- For greedy conflicts: implement a two-pass assignment or maintain a small
  manual-override CSV keyed by `(ref_id, dl_id)` to reconcile contested matches.
- For structural renames and critical missing episodes: consider a manual mapping
  table or extend download sources (archive.org, other platforms).
- Continue adding regression rows when a false negative is fixed.

---

File: [docs/ALIGNMENT_MISTAKES.md](docs/ALIGNMENT_MISTAKES.md)

***End Compact Audit***
