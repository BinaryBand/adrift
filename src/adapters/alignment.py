from typing import Any

from src.ports.alignment import AlignmentPort


class GreedyAlignmentAdapter(AlignmentPort):
    """Default greedy alignment adapter.

    For now this delegates to the existing catalog implementation. The adapter
    is a stable seam for future alternative implementations (Rust, C, etc.).
    """

    def align_episodes(self, references: list[Any], downloads: list[Any], show: str = ""):
        # Local import to avoid circular imports at module import time.
        # Delegate to the catalog implementation function to avoid recursion
        # through the public `align_episodes` wrapper.
        from src.catalog import align_episodes_impl

        return align_episodes_impl(references, downloads, show)


__all__ = ["GreedyAlignmentAdapter"]
