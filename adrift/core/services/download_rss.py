"""RSS feed regeneration for downloaded podcasts."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import requests

from adrift.core.models import PodcastConfig, RssChannel, RssEpisode
