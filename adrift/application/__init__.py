"""Application layer — use-cases that orchestrate domain + ports.

This layer contains the high-level workflows (merge, download) that
orchestrate domain logic and I/O through abstract ports.
No application code directly does I/O; all I/O goes through ports.
"""
