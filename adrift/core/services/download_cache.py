"""Cached helpers for download services (existing media sources)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from adrift.core.services.download_client import prefixed_key
from adrift.core.util.regex import YOUTUBE_VIDEO_REGEX
