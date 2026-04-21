# Podcast Feed Builder — Specification

## Models

```mermaid
classDiagram
    class SourceFilter {
        +str[] include
        +str[] exclude
        +RRule[] r_rules
    }

    class FeedSource {
        +str url
        +SourceFilter filters
    }

    class Podcast {
        +str name
        +str path
        +FeedSource[] references
        +FeedSource[] downloads
        +RRule[] schedule
    }

    class RssEpisode {
        +str id
        +str title
        +str author
        +str content
        +str description
        +float duration
        +DateTime pub_date
        +str image
    }

    class EpisodeData {
        +str id
        +str title
        +str description
        +str[] source
        +str thumbnail
        +DateTime upload_date
    }

    class MergeResult {
        +Podcast config
        +RssEpisode[] references
        +RssEpisode[] downloads
        +int[][] pairs
        +EpisodeData[] episodes
    }

    class PodcastFeed {
        +str id
        +str title
        +str author
        +str description
        +str source
        +str thumbnail
        +EpisodeData[] episodes
    }

    Podcast --> "0..*" FeedSource : references
    Podcast --> "0..*" FeedSource : downloads
    FeedSource --> "1" SourceFilter : filters
    MergeResult --> "1" Podcast : config
    MergeResult --> "0..*" RssEpisode : references
    MergeResult --> "0..*" RssEpisode : downloads
    MergeResult --> "0..*" EpisodeData : episodes
    PodcastFeed --> "0..*" EpisodeData : episodes
```

### Source URL conventions

| Scheme | Example | Description |
| --- | --- | --- |
| HTTP/S feed | `https://example.com/feed.rss` | Standard RSS/Atom feed |
| YouTube channel | `yt://@channel_handle` | Channel episode list |
| YouTube video | `yt://#video_id` | Single episode reference |

### Schedule conventions (RFC 5545)

`Podcast.schedule` is a list of recurrence definitions used to decide whether a
podcast should run on the current day.

Supported formats:

| Format | Example | Notes |
| --- | --- | --- |
| Legacy RRULE-only | `FREQ=WEEKLY;BYDAY=MO` | Backward-compatible shorthand |
| RFC 5545 DTSTART + RRULE | `DTSTART:20240124T000000Z\nRRULE:FREQ=WEEKLY;BYDAY=MO` | Preferred when a recurrence start date is required |

TOML example:

```toml
[[podcasts]]
name = "The Daily Show"
schedule = ["DTSTART:20240124T000000Z\nRRULE:FREQ=WEEKLY;BYDAY=MO"]
```

Notes:

- `DTSTART` establishes the recurrence start boundary.
- `BYDAY=MO` with this start date yields Monday occurrences from the first Monday on/after the start boundary.
- Schedule recurrence controls when a podcast is processed, not per-episode publish-date eligibility.

### References vs Downloads

`Podcast.references` and `Podcast.downloads` serve distinct roles in the build pipeline, and a single episode must have a match in both.

The cross-alignment step pairs each **download source** record with its corresponding **reference record**. The merged result carries the metadata from the reference side and the download URL from the download side.

```mermaid
flowchart LR
    REF[references - metadata sources] --> RD[Cross-aligned episode]
    DL[downloads - file sources] --> RD
    RD --> EP[EpisodeData with title, description, thumbnail and resolved download URL]
```

* * *

## Process Flow

The pipeline runs in two separate phases per podcast. Both phases respect `Podcast.schedule`.

### Phase 1 — Download

Fetch candidate episodes from both sources, cross-align them, then download only the matched subset.

```mermaid
flowchart TD
    A([Start]) --> B{today ∈ P.schedule?}
    B -- No --> Z([Skip])
    B -- Yes --> C(For each podcast → P)
    C --> X[Fetch αR from P.references]
    X --> D[Deduplicate αR → R]
    D --> E[Fetch αD from P.downloads]
    E --> F[Deduplicate αD → D]
    F --> G[Cross-align R × D → RD]
    G --> J([Download audio for each episode in RD → S3])
```

> **Note:** Steps D and F use the same 4-signal greedy matcher as the cross-alignment step (G), applied within each source list to collapse near-duplicates from overlapping feeds. The greedy algorithm prevents double-use, so no additional deduplication pass is needed after step G.

### Phase 2 — RSS Feed Rebuild

Rebuild the RSS feed from reference metadata matched against files already on S3.

```mermaid
flowchart TD
    A([Start]) --> B{today ∈ P.schedule?}
    B -- No --> Z([Skip])
    B -- Yes --> C(For each podcast → P)
    C --> D[Fetch R from P.references]
    D --> E[List audio files on S3]
    E --> F[Match R episodes to S3 filenames]
    F --> G([Emit PodcastFeed → upload feed.rss to S3])
```

> **Note:** Stage 3 merge is implemented in `merge_episode` (`src/catalog.py`) and covered by tests (see `tests/catalog/test_align_episodes.py` and `tests/catalog/test_catalog.py`), but it is not yet integrated into the Phase 2 RSS rebuild. The RSS feed is currently emitted using reference metadata only; YouTube titles, thumbnails, and descriptions are not yet used in the emitted feed.

### Tuning Parameters

| Parameter | Effect |
| --- | --- |
| `θ` (score threshold) | Higher → fewer matches, lower → more aggressive |
| `w_id` | Weight given to ID similarity |
| `w_date` | Weight given to date similarity |
| `w_title` | Weight given to title similarity |
| `w_desc` | Weight given to description similarity |

### Stage 1 — Similarity Scoring

For each pair `(e1, e2)` in the cross-product of the two episode lists, compute a weighted similarity score across up to four signals:

```text
Score(e1, e2) =  w_id   · sim_id(e1, e2)      [bonus — added after normalization]
              +  w_date  · sim_date(e1, e2)     [optional — omitted when either date is absent]
              +  w_title · sim_title(e1, e2)
              +  w_desc  · sim_desc(e1, e2)     [optional — omitted when both descriptions are empty]

sim_id(e1, e2)    — 1.0 if IDs are identical; 0.0 otherwise
sim_date(e1, e2)  — tiered by |date difference|:
                      ≤ 2 days  → 1.00
                      ≤ 10 days → 0.70
                      ≤ 35 days → 0.15
                      otherwise → 0.00
sim_title(e1, e2) — normalized title similarity
sim_desc(e1, e2)  — normalized description similarity
```

The optional signals (`w_date`, `w_desc`) are excluded from the denominator when absent, so missing metadata does not penalize pairs — the remaining signals are renormalized over the signals that are present. `w_id` is applied as an additive bonus on top of the renormalized base score rather than as part of the normalized sum, since ID matches are rare across platforms and should reward but not dominate.

A pair with no ID match, no descriptions, and a low title similarity is rejected outright without scoring.

All scored pairs are passed to the greedy matcher.

> **Cross-platform note:** Episodes compared across ID namespaces (e.g. a YouTube source vs an RSS feed) will always have `sim_id = 0.0`. Keeping `w_id` small ensures this is a modest same-platform bonus rather than an impassable gate.

### Stage 2 — Greedy Matching

Sort all scored pairs descending by score. Iterate through them: if neither episode in a pair has been matched yet, commit the pair and mark both as used. Stop when the next candidate pair's score falls below θ.

This guarantees the globally best match is always preferred first. It also prevents a near-duplicate title (e.g. a multi-part episode) from stealing a match that belongs to a higher-scoring pair — once the correct pair is committed, both episodes leave the pool.

```mermaid
flowchart TD
    A[Sort all pairs by score, desc] --> B[Next pair]
    B --> C{Score ≥ θ?}
    C -- No --> Z([Done])
    C -- Yes --> D{Both episodes unused?}
    D -- No --> B
    D -- Yes --> E[Commit pair, mark both used]
    E --> B
```

For more than two source feeds, apply iteratively: `match(match(lst1, lst2), lst3)`.

### Stage 3 — Merge

Resolve each matched pair to a single canonical `EpisodeData` using field-level precedence:

| Field | Resolution rule |
| --- | --- |
| `id` | Prefer non-URL ID; tie-break to download side (YouTube video ID › RSS GUID) |
| `title` | Longest / most punctuated (heuristic), or modal value |
| `upload_date` | Earliest date in pair |
| `description` | Longest non-empty value |
| `thumbnail` | Prefer highest-resolution (inferred from URL) |
| `source` | Union of all source URLs in pair |

> **Status:** `merge_episode` is implemented in `src/catalog.py` and covered by tests (`tests/catalog/test_align_episodes.py`, `tests/catalog/test_catalog.py`). Integration into the Phase 2 RSS rebuild remains pending.
