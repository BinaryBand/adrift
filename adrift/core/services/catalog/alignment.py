"""Episode alignment: fuzzy matching of references to downloads."""

# cspell: ignore cdist
import hashlib
import pathlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NamedTuple, cast

import requests
from diskcache import Cache
from rapidfuzz import fuzz
