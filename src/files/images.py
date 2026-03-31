from pathlib import Path
from PIL import Image
import sys
import os

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())


def make_square_image(file_path: Path, quality: int = 85) -> bool:
    try:
        if not os.path.exists(file_path):
            print(f"WARNING: Image file not found: {file_path}")
            return False

        with Image.open(file_path) as img:
            # Convert to RGB if needed (handles RGBA, P mode, etc.)
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Get dimensions and calculate crop box for center square
            width, height = img.size
            min_dimension = min(width, height)
            size = min_dimension

            # Calculate crop coordinates for center square
            left = (width - min_dimension) // 2
            top = (height - min_dimension) // 2
            right = left + min_dimension
            bottom = top + min_dimension

            # Crop to square and resize to target size
            square_img = img.crop((left, top, right, bottom))
            final_img = square_img.resize((size, size), Image.Resampling.LANCZOS)

            # Save back to the same location
            final_img.save(file_path, format="JPEG", quality=quality, optimize=True)

        return True

    except Exception as e:
        print(f"ERROR: Failed to convert image {file_path}: {e}")
        return False


def make_square_image_with_padding(
    file_path: str, size: int = 600, bg_color: tuple = (0, 0, 0), quality: int = 85
) -> bool:
    """Convert image to 1:1 aspect ratio using padding instead of cropping."""

    try:
        if not os.path.exists(file_path):
            print(f"WARNING: Image file not found: {file_path}")
            return False

        with Image.open(file_path) as img:
            # Convert to RGB if needed
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Create square canvas with background color
            square_img = Image.new("RGB", (size, size), bg_color)

            # Resize image to fit within square (maintaining aspect ratio)
            img.thumbnail((size, size), Image.Resampling.LANCZOS)

            # Center the image on the square canvas
            paste_x = (size - img.width) // 2
            paste_y = (size - img.height) // 2
            square_img.paste(img, (paste_x, paste_y))

            # Save back to the same location
            square_img.save(file_path, format="JPEG", quality=quality, optimize=True)

        return True

    except Exception as e:
        print(f"ERROR: Failed to convert image {file_path}: {e}")
        return False
