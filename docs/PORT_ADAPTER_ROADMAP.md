# Port/Adapter Roadmap

This roadmap preserves current behavior while making future swaps easier.

## Existing Baseline

- S3 secret retrieval is abstracted behind a swappable secret provider.
- Runtime validation still fails fast when required S3 values are missing.

## Next Targets

1. YouTube/RSS Source Ports
- Add `EpisodeSourcePort` with adapter implementations for:
- RSS feed extraction
- YouTube metadata extraction
- Keep existing orchestration flow in place and switch by dependency injection at boundaries.

2. Config Source Port
- Add `ConfigSourcePort` to abstract config loading from:
- local TOML files
- remote/object-backed config storage (future)
- Continue returning current model types to avoid behavior changes.

3. Storage Endpoint Selection Port
- Add a small `StorageEndpointPort` for endpoint policy:
- local-first selection
- remote fallback
- Keep current local probe semantics as default adapter behavior.

## RSS Pydantic Simplification (Phased)

Goal: simplify XML -> Podcast conversion without changing output behavior.

Phase 1: Boundary Models
- Introduce Pydantic models only for parsed channel/entry boundary data.
- Keep XML parsing and traversal logic unchanged.

Phase 2: Normalization Models
- Normalize enclosure/content/image variants through narrow validators.
- Preserve existing fallback precedence rules.

Phase 3: Pipeline Cleanup
- Replace selected ad-hoc dict/object branching with model validation helpers.
- Keep final `RssChannel` and `RssEpisode` outputs identical.

## Guardrails

- Prefer additive adapters and wrapper helpers over broad rewrites.
- Preserve existing public signatures unless migration wrappers are provided.
- For each phase, run full quality and test matrix before continuing.
