"""Legacy default adapters implementing the merge collaborator ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from adrift.core.models import (
    EpisodeData,
    PodcastConfig,
    ReferenceMatchTrace,
    RssEpisode,
    SourceTrace,
)

from .alignment import merge_episode
from .collection import EpisodeFetchContext, _collect_episodes_with_traces
from .merge_trace import _build_match_traces

from adrift.core.ports import Callback, EpisodeSourceFactoryPort, ScoredAlignmentBatchPort

_TRACE_BUILD_ARITY = 5
_EPISODE_MERGE_ARITY = 3
