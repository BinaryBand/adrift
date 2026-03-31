# Plan: Consolidate runbooks, kill compat shims, prune dead audio code

## Context

The SPECS.md migration is complete: configs are fully migrated to the new TOML format
(`name`/`references`/`downloads`), and the new matching/merge logic is in place.
Three cleanup tasks remain:

1. The three-file runbook structure (`download.py` → subprocess → `podcasts/download_podcasts.py`
   → subprocess → `podcasts/update_podcasts.py`) is needlessly split. Merge into a single
   `runbook/download.py`.
2. Backward-compat shims in `src/app_common.py` (model validator, aliases, legacy properties)
   exist only to support the old TOML format, which is fully migrated. Remove them.
3. The scipy/numpy audio feature-extraction pipeline (`get_feats`, `calc_feat_distance`,
   `find_silent_segments`, etc.) was experimental dead code — never called from production paths.
   Remove it and its unused dependencies.

---

## Phase 1 — Merge runbooks into `runbook/download.py`

### Current structure

```text
runbook/download.py          — orchestrator: calls the two below as subprocesses
runbook/podcasts/
  download_podcasts.py       — audio download logic
  update_podcasts.py         — RSS feed rebuild logic
```

### Target structure

```text
runbook/download.py          — single file with all logic, no subprocess calls
```

### What to do

Inline both scripts into `runbook/download.py`. The result runs in one process:

1. Parse `--include` args, default to `DF_TARGETS = ["config/podcasts.toml", "config/youtube.toml"]`
2. Call `load_podcasts_config(include=...)` once
3. For each `PodcastConfig`: call `_download_series(config)` then `_update_series(config)`

Keep `--skip-download` / `--skip-update` flags so the two phases can be run independently.

The subprocess invocations in the current `download.py` are replaced with direct function calls.
Remove the `sys.path` hacks and relative imports that exist only because of the subprocess split.

**Delete**: `runbook/podcasts/download_podcasts.py`, `runbook/podcasts/update_podcasts.py`, and
the now-empty `runbook/podcasts/` directory.

---

## Phase 2 — Kill backward-compat shims in `src/app_common.py`

The TOML files are fully migrated. No legacy-format input paths remain.

### Remove

1. `model_validator(mode="before")` `_migrate_legacy_fields` — the entire method
2. `FilterRules = SourceFilter` alias
3. `PodcastData = PodcastConfig` alias
4. `.title` property (`return self.name`)
5. `.feeds` property (`return [fs.url for fs in self.references]`)
6. `.sources` property (`return [fs.url for fs in self.downloads]`)
7. `.filters` property
8. `.feed_filters` property (always returned `None`)
9. `.source_filters` property (always returned `None`)

### Update callers

After the runbook merge in Phase 1, grep for any remaining `.title` / `.feeds` / `.sources`
accesses and update to `.name` / `.references` / `.downloads`.

`src/catalog.py`: `process_channel()` already uses `config.references` — verify no `.feeds`
references remain.

### Fix stale log path

`LOG_PATH = Path(".logs") / DEVICE` but `get_match_data` uses `Path(".log") / DEVICE` (missing `s`).
Normalize to `.logs`.

---

## Phase 3 — Prune `src/files/audio.py`

### Remove (dead feature-extraction pipeline)

All of these have no production callers (only dead tests):

| Symbol | Reason |
| --- | --- |
| `_NOISE_DB`, `_SAMPLE_RATE` | Only used by removed functions |
| `LAX_SIMILARITY`, `LAX_EUCLIDEAN`, `STRICT_SIMILARITY`, `STRICT_EUCLIDEAN` | Never used anywhere |
| `MIN_AD_LENGTH`, `MIN_BLOCK_LENGTH` | Never used anywhere |
| `_FULL_AUDIO_CACHE` (LRU) | Only used by `_get_feats` |
| `_FEATS_CACHE` (diskcache) | Only used by `get_feats` |
| `_SILENCE_CACHE` (diskcache) | Only used by `find_silent_segments` |
| `_trim_audio_silence(audio_data)` | Only used by `get_feats` |
| `_get_feats(file, start, end)` | Only used by `get_feats`, `prefetch_full_audio` |
| `calc_feat_distance(lhs, rhs)` | No production caller |
| `get_feats(file, start, end)` | No production caller |
| `prefetch_full_audio(file)` | No caller at all |
| `find_silent_segments(file)` | No production caller |
| `copy_segments(file, segments, ...)` | No caller at all |
| `extract_segment(file, start, end, dest)` | No production caller |

Also remove `import scipy...` and `import numpy as np`.

### Keep (active in production pipeline)

`handle_subprocess_error`, `is_audio`, `parse_duration`, `get_duration`, `invert_segments`,
`_cut_segments`, `cut_segments`, `MIN_LENGTH`, `AUDIO_EXTENSIONS`.

### Delete test files for removed functions

- `tests/audio/test_audio_matching.py`
- `tests/audio/test_extract_features.py`
- `tests/audio/test_silence_detection.py`
- `tests/audio/test_extract_segment.py`

Keep `tests/audio/test_cut_segments.py` — tests `cut_segments` / `invert_segments` which are active.

---

## Phase 4 — Prune `requirements.txt`

All of the following have zero imports anywhere in the codebase (confirmed by grep):

| Package | Reason |
| --- | --- |
| `annoy` | Zero imports |
| `optuna` | Zero imports |
| `scipy` | Only used in removed audio feature pipeline |
| `scipy-stubs` | Type stubs for removed scipy |
| `numpy` | Only used in removed audio feature pipeline |
| `scrapy` | Zero imports |
| `portion` | Zero imports |
| `flask` | Zero imports |
| `tabulate` | Zero imports |

---

## Phase 5 — Catalog cleanup

Remove `similarity(a, b)` from `src/catalog.py` — superseded by `_similarity_clean` (pre-normalized
inputs). No external callers.

`align_episodes` and `merge_episode` are implemented but not yet wired into any production call
path. Leave them — they are the spec's cross-alignment logic pending a `process_podcast()`
orchestrator. Do not remove.

---

## Execution order

Phases 3, 4, and 5 are independent and can be done in any order or in parallel.
Phase 1 (runbook merge) should come before Phase 2 (kill shims), since the runbook
is the primary caller of the legacy `.title` / `.feeds` / `.sources` properties.

---

## Verification

1. `python runbook/validate_configs.py` — all TOML entries load correctly
2. `pytest tests/` — remaining tests pass; deleted test files are gone
3. `mypy src/ runbook/` — no new type errors
4. `python runbook/download.py --skip-download --include config/podcasts.toml` — RSS update
   completes without errors
