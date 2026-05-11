from src.models import RssEpisode
from src.ports import AlignmentPort


class GreedyAlignmentAdapter(AlignmentPort):
    """Default greedy alignment adapter.

    Delegates to the existing catalog implementation. This is a stable seam for
    future alternative implementations (Rust, C, etc.).
    """

    def align_episodes(
        self, references: list[RssEpisode], downloads: list[RssEpisode], show: str = ""
    ) -> list[tuple[int, int]]:
        # Local import to avoid circular imports at module import time.
        # Delegate to the catalog implementation function to avoid recursion
        # through the public `align_episodes` wrapper.
        from src.catalog import align_episodes_impl

        return align_episodes_impl(references, downloads, show)


__all__ = ["GreedyAlignmentAdapter"]
