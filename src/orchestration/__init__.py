"""Legacy compatibility package.

Application-level coordination code now lives under src.application.services.
This package remains as a narrow import shim during migration.
"""

from src.application.services import *  # noqa: F401,F403
