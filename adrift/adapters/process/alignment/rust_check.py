"""Detect and compile Rust alignment extension if needed.

This module handles:
1. Checking if the Rust extension is available
2. Auto-compiling if not available and environment allows
3. Defaulting to Rust backend if available
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from importlib import import_module
from pathlib import Path

logger = logging.getLogger(__name__)

_EXTENSION_MODULE = "adrift_rust_alignment"
_MANIFEST_PATH = "rust/adrift_rust_alignment/Cargo.toml"

_compile_result: bool | None = None


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


def _run_maturin_compile() -> bool:
    """Invoke maturin to build the extension; log and return the outcome."""
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
        succeeded = result.returncode == 0 and can_load_rust_extension()
        if not succeeded:
            logger.warning(
                "Rust alignment extension compile failed; falling back to Python. %s",
                result.stderr.strip()[-2000:],
            )
        return succeeded
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.warning(
            "Rust alignment extension compile errored (%s); falling back to Python.", exc
        )
        return False


def try_compile_rust_extension() -> bool:
    """Try to compile the Rust extension using maturin.

    Returns True if compilation succeeded or extension is already available.
    The outcome is cached per-process so a failing compile is only attempted
    once, instead of re-running the maturin subprocess on every call.
    """
    global _compile_result
    if _compile_result is not None:
        return _compile_result
    if can_load_rust_extension():
        _compile_result = True
        return True
    if should_skip_rust_compilation() or not Path(_MANIFEST_PATH).exists():
        _compile_result = False
        return False

    logger.info("Rust alignment extension not found; compiling via maturin...")
    _compile_result = _run_maturin_compile()
    return _compile_result


def should_use_rust_backend() -> bool:
    """Determine if Rust backend should be used.

    1. If env var explicitly sets backend, respect it.
    2. Otherwise, try to make Rust available and use it if successful.
    """
    explicit_backend = os.getenv("ADRIFT_ALIGNMENT_BACKEND", "").lower()
    if explicit_backend:
        return explicit_backend == "rust"

    return try_compile_rust_extension()


def ensure_rust_alignment_backend() -> bool:
    """Guard called by CLI runners before the alignment stage: make sure the
    Rust extension is compiled if possible, logging which engine will run.

    Returns True if Rust will be used, False if callers should expect the
    pure-Python fallback.
    """
    using_rust = should_use_rust_backend()
    if using_rust:
        logger.info("Alignment backend: Rust")
    else:
        logger.info("Alignment backend: Python (Rust unavailable)")
    return using_rust
