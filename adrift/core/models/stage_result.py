"""Railway-oriented pipeline abstraction.

StageResult[T] carries both success and failure forward through a pipeline.
Errors accumulate; nothing is swallowed. The caller sees both the value
and all warnings/errors encountered along the way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

from adrift.core.models.errors import PipelineError

T = TypeVar("T")
