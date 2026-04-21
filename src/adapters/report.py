from pathlib import Path

from src.models import MergeResult
from src.ports import ReportDocument, ReportRenderOptions, compose
from src.reporting.sections import DEFAULT_DOCUMENTS


def _coerce_render_options(options: ReportRenderOptions | None) -> ReportRenderOptions:
    return options or ReportRenderOptions()


def _documents(options: ReportRenderOptions) -> tuple[ReportDocument, ...]:
    return options.documents or DEFAULT_DOCUMENTS


class FileReportAdapter:
    """File-backed report adapter that writes markdown report documents."""

    def generate_reports(
        self,
        result: MergeResult,
        output_root: Path,
        options: ReportRenderOptions | None = None,
    ) -> list[Path]:
        render_options = _coerce_render_options(options)
        out_dir = Path(output_root) / result.config.slug / "feeds"
        out_dir.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []
        for document in _documents(render_options):
            out_path = out_dir / document.filename
            if out_path.exists() and not render_options.overwrite:
                written.append(out_path)
                continue

            markdown = compose(result, document.sections, sep=document.sep).rstrip() + "\n"
            out_path.write_text(markdown, encoding="utf-8")
            written.append(out_path)

        return written


__all__ = ["FileReportAdapter"]
