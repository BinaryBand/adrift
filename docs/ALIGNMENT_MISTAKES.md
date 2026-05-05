# Alignment Mistakes: Morbid Audit Snapshot

This note summarizes what is going wrong in the current Morbid alignment run, based on:
- `downloads/morbid/manual_matches_review.csv`
- `downloads/morbid/manual_matches_audit_detailed.csv`
- `downloads/morbid/manual_matches_audit_summary.json`

## At a Glance

Total reviewed: 518

| Category | Count | What it means |
| --- | ---: | --- |
| `likely_no_matching_download` | 180 | Reference likely has no real counterpart in current download source coverage |
| `problematic_series_mismatch` | 67 | Same series matched to wrong numbered item (for example Listener Tales `N` -> wrong `N`) |
| `problematic_reused_target` | 20 | One generic target is reused across many weak matches |
| `problematic_misrank` | 13 | A better lexical candidate appears to exist, but was not selected |
| `problematic_part_mismatch` | 2 | Same title family, wrong part number |
| `likely_correct_variant` | 55 | Looks like acceptable title variant |
| `unclear` | 181 | Needs manual review |

## Mistake Types with Examples

### 1) Missing from Source Coverage
Reference appears valid, but no strong download candidate exists.

Examples:
- `ref 556`: "Tara Calico" -> "Mamie Thurman" (`best_score=0.2487`)
- `ref 622`: "Susan Wright" -> "Caryl Chessman: The Red Light Bandit" (`best_score=0.2543`)
- `ref 825`: "Hinterkaifek" -> "Listener Tales 81" (`best_score=0.2698`)

Interpretation:
- These are mostly not ranking mistakes; they are absent or underrepresented in the current YouTube corpus.

### 2) Series Number Mismatch
The matcher aligns by broad phrase overlap but ignores series index semantics.

Examples:
- `ref 386`: "Listener Tales 59" -> "Listener Tales 109"
- `ref 516`: "Listener Tales 34" -> "Listener Tales 83"
- `ref 636`: "Listener Tales 21" -> "Listener Tales 82"

Interpretation:
- Title similarity is high, but the episode number is wrong.

### 3) Reused Generic Target
A small set of episodes are repeatedly selected for many unrelated references.

Examples:
- `download_index 242` selected by 13 references
- `download_index 22` selected by 11 references
- `download_index 241` selected by 11 references

Representative rows:
- `ref 468`: "Spooky New Orleans Vol. 1" -> "Spooky Lakes (Volume 2)"
- `ref 704`: "The Mysterious Murder of Karina Holmer" -> "The Mysterious Death of Charles Morgan"

Interpretation:
- Generic terms drive false positives when stronger constraints are absent.

### 4) Misrank (Better Candidate Exists)
A higher-quality candidate is likely available, but current scoring/greedy ordering picks another one.

Examples:
- `ref 752`: "Lizzie Borden Part 2" -> "Burke & Hare, Part 2"
- `ref 441`: "Jack the Ripper Part 2" -> "Jack Tupper, Part 2"
- `ref 419`: "Spooky Lakes Vol. 1" -> "Spooky Lakes (Volume 2)"

Interpretation:
- Candidate set is not always the issue; ranking and constraints are.

### 5) Part Mismatch
Part-number family matches but wrong part index.

Examples:
- `ref 417`: "JonBenet Ramsey Part 2" -> "JonBenet Ramsey Part 1"
- `ref 369`: "Theodore Durrant Part 2" -> "Theodore Durrant Part 1"

Interpretation:
- Part number needs stricter handling than plain lexical similarity.

## Why This Happens

1. Coverage mismatch: references span 2018-2026, downloads mostly cover late 2022-2026.
2. Numeric semantics are weakly enforced: `Listener Tales N`, `Part N`, `Vol N` are treated mostly as text.
3. Greedy global assignment can lock in bad early matches.
4. Generic phrasing in titles increases accidental overlap.

## Suggested Use of This Doc

Use these categories as triage labels during review:
- `missing_source`: do not force-match.
- `series_or_part_mismatch`: block until number-consistent candidate exists.
- `misrank`: inspect top-N alternatives.
- `reused_target`: treat as likely false positive unless strong corroborating signals exist.
