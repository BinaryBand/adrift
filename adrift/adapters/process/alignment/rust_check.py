"""Detect and compile Rust alignment extension if needed.

This module handles:
1. Checking if the Rust extension is available
2. Auto-compiling if not available and environment allows
3. Defaulting to Rust backend if available
"""

from __future__ import annotations

import os
import subprocess
import sys
from importlib import import_module
from pathlib import Path

_EXTENSION_MODULE = "adrift_rust_alignment"
_MANIFEST_PATH = "rust/adrift_rust_alignment/Cargo.toml"


def can_load_rust_extension() -> bool:
    """Check if the Rust extension can be imported."""
    try:
        import_module(_EXTENSION_MODULE)
        return True
    except ModuleNotFoundError:
        return False


def should_skip_rust_compilation() -> bool:
    """Check if Rust compilation should be skipped."""
    skip_vars = ["ADRIFT_SKIP_RUST_COMPILE", "SKIP_RUST_COMPILE"]
    for var in skip_vars:
        if os.getenv(var, "").lower() in ("1", "true", "yes"):
            return True
    return False


def try_compile_rust_extension() -> bool:
    """Try to compile the Rust extension using maturin.

    Returns True if compilation succeeded or extension is already available.
    """
    if can_load_rust_extension():
        return True
    if should_skip_rust_compilation() or not Path(_MANIFEST_PATH).exists():
        return False
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maturin",
                "develop",
                "--release",
                "--manifest-path",
                _MANIFEST_PATH,
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        return result.returncode == 0 and can_load_rust_extension()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def should_use_rust_backend() -> bool:
    """Determine if Rust backend should be used.

    1. If env var explicitly sets backend, respect it.
    2. Otherwise, try to make Rust available and use it if successful.
    """
    explicit_backend = os.getenv("ADRIFT_ALIGNMENT_BACKEND", "").lower()
    if explicit_backend:
        return explicit_backend == "rust"

    if try_compile_rust_extension():
        return True

    return False
