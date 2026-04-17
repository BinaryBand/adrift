from typing import Protocol

from src.models.metadata import RssEpisode


class AlignmentPort(Protocol):
    """Port for aligning reference and download episode lists."""

    def align_episodes(
        self,
        references: list[RssEpisode],
        downloads: list[RssEpisode],
        show: str = "",
    ) -> list[tuple[int, int]]:
        """Return matched (reference_index, download_index) pairs."""
        ...
