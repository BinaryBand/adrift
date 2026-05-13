from typing import Protocol

from adrift.models import AlignmentConfig, RssEpisode


class AlignmentPort(Protocol):
    """Port for aligning reference and download episode lists."""

    def align_episodes(
        self,
        references: list[RssEpisode],
        downloads: list[RssEpisode],
        alignment: AlignmentConfig | None = None,
    ) -> list[tuple[int, int]]:
        """Return matched (reference_index, download_index) pairs using alignment config."""
        ...
