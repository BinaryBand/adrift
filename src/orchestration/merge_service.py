"""Compatibility shim for legacy merge service imports."""

from src.application.services.merge_service import (
    MergeRunOptions,
    MergeWriters,
    emit_timings,
    format_duration,
    model_payloads,
    series_output_paths,
    write_json,
    write_output_bundle,
    write_report_file,
    write_series_outputs,
)

__all__ = [
    "MergeRunOptions",
    "MergeWriters",
    "emit_timings",
    "format_duration",
    "model_payloads",
    "series_output_paths",
    "write_json",
    "write_output_bundle",
    "write_report_file",
    "write_series_outputs",
]
