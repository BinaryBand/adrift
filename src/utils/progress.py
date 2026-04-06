from typing import Any, Callable

from tqdm import tqdm

Callback = Callable[[int, int | None], None]


def get_callback(progress: tqdm[Any]) -> Callback:
    """Create a callback function for progress tracking."""

    def callback(value: int, total_value: int | None) -> None:
        if total_value and progress.total != total_value:
            progress.total = total_value
            progress.refresh()

        delta = value - progress.n
        if delta > 0:
            progress.update(delta)

    return callback
