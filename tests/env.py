"""Shared test environment defaults.

This module centralises commonly-set environment variables used by unit
tests so individual test files avoid duplicating the same `os.environ`
boilerplate (which triggers copy/paste detection).
"""

import os

os.environ.setdefault("S3_USERNAME", "_test")
os.environ.setdefault("S3_SECRET_KEY", "_test")
os.environ.setdefault("S3_ENDPOINT", "http://localhost")
os.environ.setdefault("S3_REGION", "us-east-1")
