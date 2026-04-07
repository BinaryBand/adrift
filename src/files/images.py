import os
import sys
from pathlib import Path
from typing import Any

from PIL import Image

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())


def _crop_to_center_square(img: Any) -> Any:
    width, height = img.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    return img.crop((left, top, left + side, top + side)).resize(
        (side, side), resample=int(Image.Resampling.LANCZOS)
    )


def _paste_centered(canvas: Any, img: Any) -> None:
    img.thumbnail(canvas.size, Image.Resampling.LANCZOS)
    paste_x = (canvas.width - img.width) // 2
    paste_y = (canvas.height - img.height) // 2
    canvas.paste(img, (paste_x, paste_y))


def make_square_image(file_path: Path, quality: int = 85) -> bool:
    return make_square_image_to(file_path, file_path, output_format="JPEG", quality=quality)


def make_square_image_to(
    input_path: Path,
    output_path: Path,
    output_format: str = "WEBP",
    quality: int = 80,
) -> bool:
    try:
        if not os.path.exists(input_path):
            print(f"WARNING: Image file not found: {input_path}")
            return False

        with Image.open(input_path) as img:
            if img.mode != "RGB":
                img = img.convert("RGB")
            final_img = _crop_to_center_square(img)
            save_args = {"format": output_format, "quality": quality, "optimize": True}
            if output_format == "WEBP":
                save_args["method"] = 6
            final_img.save(output_path, **save_args)

        return True

    except Exception as e:
        print(f"ERROR: Failed to convert image {input_path}: {e}")
        return False


DEFAULT_PADDING_BG_COLOR = (0, 0, 0)


def make_square_image_with_padding(
    file_path: str,
    size: int = 600,
    bg_color: tuple[int, int, int] = DEFAULT_PADDING_BG_COLOR,
    quality: int = 85,
) -> bool:
    """Convert image to 1:1 aspect ratio using padding instead of cropping."""
    try:
        if not os.path.exists(file_path):
            print(f"WARNING: Image file not found: {file_path}")
            return False

        with Image.open(file_path) as img:
            if img.mode != "RGB":
                img = img.convert("RGB")
            square_img = Image.new("RGB", (size, size), bg_color)
            _paste_centered(square_img, img)
            square_img.save(file_path, format="JPEG", quality=quality, optimize=True)

        return True

    except Exception as e:
        print(f"ERROR: Failed to convert image {file_path}: {e}")
        return False
