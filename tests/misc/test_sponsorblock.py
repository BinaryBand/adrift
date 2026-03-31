"""Tests for SponsorBlock API integration."""

from unittest.mock import Mock, patch
from pathlib import Path
import unittest
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.web.sponsorblock import (
    SponsorSegment,
    _fetch_sponsor_segments,
    fetch_sponsor_segments,
    remove_sponsors,
)


class TestSponsorSegment(unittest.TestCase):
    """Test the SponsorSegment model."""

    def test_create_segment(self):
        """Test creating a segment with API field names."""
        data = {
            "segment": [10.5, 25.3],
            "UUID": "abc123",
            "category": "sponsor",
            "videoDuration": 300.0,
            "actionType": "skip",
            "locked": 0,
            "votes": 5,
        }
        segment = SponsorSegment(**data)

        self.assertEqual(segment.segment, (10.5, 25.3))
        self.assertEqual(segment.uuid, "abc123")
        self.assertEqual(segment.category, "sponsor")
        self.assertEqual(segment.action_type, "skip")
        self.assertEqual(segment.video_duration, 300.0)

    def test_segment_with_tuple(self):
        """Test creating segment with tuple."""
        segment = SponsorSegment(
            segment=(1.0, 2.0),
            UUID="test",
            category="intro",
            videoDuration=100.0,
            actionType="mute",
            locked=0,
            votes=3,
        )
        self.assertIsInstance(segment.segment, tuple)
        self.assertEqual(segment.segment, (1.0, 2.0))


class TestFetchSponsorSegments(unittest.TestCase):
    """Test sponsor segment fetching."""

    @patch("src.web.sponsorblock._CACHE")
    @patch("src.web.sponsorblock.requests.get")
    def test_fetch_from_api(self, mock_get, mock_cache):
        """Test fetching segments from API."""
        mock_cache.get.return_value = None

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "segment": [10.0, 20.0],
                "UUID": "seg1",
                "category": "sponsor",
                "videoDuration": 300.0,
                "actionType": "skip",
                "locked": 0,
                "votes": 5,
            },
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = _fetch_sponsor_segments("test_id")

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], SponsorSegment)
        self.assertEqual(result[0].segment, (10.0, 20.0))
        mock_cache.set.assert_called_once()

    @patch("src.web.sponsorblock._CACHE")
    def test_fetch_from_local_cache(self, mock_cache):
        """Test fetching from local disk cache."""
        cached_segment = SponsorSegment(
            segment=(5.0, 15.0),
            UUID="cached",
            category="intro",
            videoDuration=200.0,
            actionType="skip",
            locked=0,
            votes=10,
        )
        mock_cache.get.return_value = [cached_segment]

        result = _fetch_sponsor_segments("cached_id")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].segment, (5.0, 15.0))

    @patch("src.web.sponsorblock._CACHE")
    @patch("src.web.sponsorblock.requests.get")
    def test_fetch_wrapped_format(self, mock_get, mock_cache):
        """Test fetching with wrapped API response format (real-world case)."""
        mock_cache.get.return_value = None

        # Real-world API response format with wrapped structure
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "videoID": "YEoxZu4Q8Ws",
                "hash": "fd86921b89f2b04d14d0",
                "segments": [
                    {
                        "category": "sponsor",
                        "actionType": "skip",
                        "segment": [1042.938, 1131.92],
                        "UUID": "fdb684db37e716e748fa9f46a14cbbb005e543d69b977055c0be753f638861657",
                        "videoDuration": 5502.121,
                        "locked": 0,
                        "votes": 0,
                        "description": "",
                    }
                ],
            }
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = _fetch_sponsor_segments("YEoxZu4Q8Ws")

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], SponsorSegment)
        self.assertEqual(result[0].segment, (1042.938, 1131.92))
        self.assertEqual(result[0].category, "sponsor")
        mock_cache.set.assert_called_once()

    @patch("src.web.sponsorblock._CACHE")
    @patch("src.web.sponsorblock.requests.get")
    def test_fetch_404_returns_empty(self, mock_get, mock_cache):
        """Test that 404 response returns empty list."""
        mock_cache.get.return_value = None

        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = _fetch_sponsor_segments("no_segments_id")

        self.assertEqual(result, [])
        mock_cache.set.assert_called_once()

    @patch("src.web.sponsorblock._CACHE")
    @patch("src.web.sponsorblock.requests.get")
    def test_fetch_invalid_response(self, mock_get, mock_cache):
        """Test handling of invalid API response."""
        mock_cache.get.return_value = None

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"invalid": "format"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = _fetch_sponsor_segments("invalid_id")

        self.assertEqual(result, [])

    @patch("src.web.sponsorblock._CACHE")
    @patch("src.web.sponsorblock.requests.get")
    def test_fetch_network_error(self, mock_get, mock_cache):
        """Test handling of network errors."""
        mock_cache.get.return_value = None
        mock_get.side_effect = Exception("Connection error")

        result = _fetch_sponsor_segments("error_id")

        self.assertEqual(result, [])


class TestPublicAPI(unittest.TestCase):
    """Test public API functions."""

    @patch("src.web.sponsorblock._fetch_sponsor_segments")
    def test_fetch_sponsor_segments_returns_tuples(self, mock_fetch):
        """Test that public API returns list of tuples."""
        mock_fetch.return_value = [
            SponsorSegment(
                segment=(10.0, 20.0),
                UUID="t1",
                category="sponsor",
                videoDuration=300.0,
                actionType="skip",
                locked=0,
                votes=5,
            ),
            SponsorSegment(
                segment=(30.0, 40.0),
                UUID="t2",
                category="intro",
                videoDuration=300.0,
                actionType="skip",
                locked=0,
                votes=10,
            ),
        ]

        result = fetch_sponsor_segments("test_id")

        self.assertEqual(result, [(10.0, 20.0), (30.0, 40.0)])

    @patch("src.web.sponsorblock._fetch_sponsor_segments")
    def test_fetch_sponsor_segments_empty(self, mock_fetch):
        """Test fetching when no segments exist."""
        mock_fetch.return_value = []

        result = fetch_sponsor_segments("empty_id")

        self.assertEqual(result, [])

    @patch("src.web.sponsorblock.cut_segments")
    @patch("src.web.sponsorblock.fetch_sponsor_segments")
    def test_remove_sponsors_success(self, mock_fetch, mock_cut):
        """Test successful sponsor removal."""
        mock_fetch.return_value = [(10.0, 20.0), (30.0, 40.0)]

        result = remove_sponsors(Path("/fake/video.mp4"), "test_id")

        self.assertTrue(result)
        mock_cut.assert_called_once_with(
            Path("/fake/video.mp4"), [(10.0, 20.0), (30.0, 40.0)], callback=None
        )

    @patch("src.web.sponsorblock.fetch_sponsor_segments")
    def test_remove_sponsors_no_segments(self, mock_fetch):
        """Test removal when no segments found."""
        mock_fetch.return_value = []

        result = remove_sponsors(Path("/fake/video.mp4"), "test_id")

        self.assertFalse(result)

    @patch("src.web.sponsorblock.cut_segments")
    @patch("src.web.sponsorblock.fetch_sponsor_segments")
    def test_remove_sponsors_handles_errors(self, mock_fetch, mock_cut):
        """Test error handling during segment removal."""
        mock_fetch.return_value = [(10.0, 20.0)]
        mock_cut.side_effect = Exception("Cut failed")

        result = remove_sponsors(Path("/fake/video.mp4"), "test_id")

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
