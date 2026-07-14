"""Catalog use-cases: collection, alignment, and merge orchestration."""

# pyright: reportPrivateUsage=false

from .alignment import (
    align_episodes,
    align_episodes_impl,
    match,
    merge_episode,
    merge_episode_pairs,
    prepare_alignment_batch,
    sim_date,
)
from .collection import (
    EpisodeFetchContext,
    process_feeds,
    process_sources,
)
from .merge import (
    MergeConfigOptionOverrides,
    MergeConfigOptions,
    merge_config,
)

__all__ = [
    "EpisodeFetchContext",
    "MergeConfigOptionOverrides",
    "MergeConfigOptions",
    "align_episodes",
    "align_episodes_impl",
    "match",
    "merge_config",
    "merge_episode",
    "merge_episode_pairs",
    "prepare_alignment_batch",
    "process_feeds",
    "process_sources",
    "sim_date",
]
