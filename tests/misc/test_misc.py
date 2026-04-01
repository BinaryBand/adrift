"""
Miscellaneous tests for small bug fixes and edge cases.
This file is for quick, focused tests that don't fit neatly into other test files.
"""

from unittest.mock import patch, MagicMock, mock_open
from urllib.parse import urlparse
from pathlib import Path
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())


def test_upload_thumbnail_returns_valid_url_format():
    """
    Test that upload_thumbnail returns URLs with forward slashes, not backslashes.

    This was a bug where Path operations on Windows could introduce backslashes
    into the returned URL, making it invalid.
    """
    from src.web.rss import upload_thumbnail

    # Mock the S3 operations
    with (
        patch("src.web.rss.exists") as mock_exists,
        patch("src.web.rss.S3_ENDPOINT", "https://s3.example.com/"),
    ):
        # Simulate an existing file (the common case)
        mock_exists.return_value = "test-id.jpg"

        result = upload_thumbnail(
            thumbnail_url="https://example.com/thumb.jpg",
            author="Test Author",
            id="test-id",
        )

        # Verify URL format
        assert result is not None, "upload_thumbnail should return a URL"
        assert "\\" not in result, f"URL should not contain backslashes: {result}"
        assert "podcasts/test-author/thumbnails/test-id.jpg" in result

        # Verify it's a valid URL that can be parsed
        parsed = urlparse(result)
        assert parsed.scheme in ("http", "https"), "URL should have http/https scheme"
        assert parsed.netloc, "URL should have a network location"


def test_upload_thumbnail_new_file_returns_valid_url():
    """
    Test that upload_thumbnail returns valid URL when uploading a new file.
    """
    from src.web.rss import upload_thumbnail

    with (
        patch("src.web.rss.exists") as mock_exists,
        patch("src.web.rss.requests.get") as mock_get,
        patch("src.web.rss.upload_file") as mock_upload_file,
        patch("src.web.rss.make_square_image"),
        patch("builtins.open", mock_open()),
    ):
        # Simulate no existing file
        mock_exists.return_value = None

        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.content = b"fake image data"
        mock_get.return_value = mock_response

        # Mock upload_file to return a URL with forward slashes
        mock_upload_file.return_value = (
            "https://s3.example.com/media/podcasts/test-author/thumbnails/test-id.jpg"
        )

        result = upload_thumbnail(
            thumbnail_url="https://example.com/thumb.jpg",
            author="Test Author",
            id="test-id",
        )

        # Verify URL format
        assert result is not None, "upload_thumbnail should return a URL"
        assert "\\" not in result, f"URL should not contain backslashes: {result}"

        # Verify it's a valid URL
        parsed = urlparse(result)
        assert parsed.scheme in ("http", "https")


def test_upload_thumbnail_handles_special_characters_in_author():
    """
    Test that author names with special characters are properly slugified.
    """
    from src.web.rss import upload_thumbnail

    with (
        patch("src.web.rss.exists") as mock_exists,
        patch("src.web.rss.S3_ENDPOINT", "https://s3.example.com/"),
    ):
        mock_exists.return_value = "test-id.jpg"

        # Test with author name containing spaces and special characters
        result = upload_thumbnail(
            thumbnail_url="https://example.com/thumb.jpg",
            author="Test Author & Co.!",
            id="test-id",
        )

        assert result is not None
        assert "\\" not in result
        # Slug should convert special characters
        assert "test-author" in result.lower()


def test_upload_thumbnail_returns_none_on_error():
    """
    Test that upload_thumbnail returns None when an error occurs.
    """
    from src.web.rss import upload_thumbnail

    with patch("src.web.rss.exists") as mock_exists:
        # Simulate an error in exists()
        mock_exists.side_effect = Exception("S3 connection failed")

        result = upload_thumbnail(
            thumbnail_url="https://example.com/thumb.jpg",
            author="Test Author",
            id="test-id",
        )

        # Should gracefully return None on error
        assert result is None


if __name__ == "__main__":
    # Run tests
    test_upload_thumbnail_returns_valid_url_format()
    test_upload_thumbnail_new_file_returns_valid_url()
    test_upload_thumbnail_handles_special_characters_in_author()
    test_upload_thumbnail_returns_none_on_error()
    print("✅ All misc tests passed!")
