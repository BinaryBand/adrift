"""Tests for audio matching functions."""

from pathlib import Path
import numpy as np
import unittest
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.files.audio import calc_feat_distance


class TestCalculateSegmentDistances(unittest.TestCase):
    """Test cases for calc_feat_distance function."""

    def test_identical_segments(self):
        """Test distance between identical segments."""
        segment = np.random.randn(100).astype(np.float32)

        cos_sim, eucl_dist = calc_feat_distance(segment, segment)

        # Cosine similarity should be 1.0 (or very close)
        self.assertAlmostEqual(cos_sim, 1.0, delta=0.001)
        # Euclidean distance should be 0.0 (or very close)
        self.assertLess(eucl_dist, 0.001)

    def test_different_segments(self):
        """Test distance between different segments."""
        segment1 = np.random.randn(100).astype(np.float32)
        segment2 = np.random.randn(100).astype(np.float32)

        cos_sim, eucl_dist = calc_feat_distance(segment1, segment2)

        # Cosine similarity should be less than 1.0
        self.assertLess(cos_sim, 1.0)
        # Euclidean distance should be positive
        self.assertGreater(eucl_dist, 0.0)

    def test_different_length_segments(self):
        """Test distance with different length segments (should be padded)."""
        segment1 = np.random.randn(100).astype(np.float32)
        segment2 = np.random.randn(150).astype(np.float32)

        cos_sim, eucl_dist = calc_feat_distance(segment1, segment2)

        # Should handle padding and return valid distances (numpy types are ok)
        self.assertTrue(isinstance(cos_sim, (float, np.floating)))
        self.assertTrue(isinstance(eucl_dist, (float, np.floating)))
        self.assertTrue(np.isfinite(cos_sim))
        self.assertTrue(np.isfinite(eucl_dist))

    def test_empty_segments(self):
        """Test distance with empty segments."""
        segment1 = np.array([], dtype=np.float32)
        segment2 = np.random.randn(100).astype(np.float32)

        cos_sim, eucl_dist = calc_feat_distance(segment1, segment2)

        # Empty segments should return 0 similarity and infinite distance
        self.assertEqual(float(cos_sim), 0.0)
        self.assertEqual(float(eucl_dist), float("inf"))

    def test_similar_segments(self):
        """Test distance between similar but not identical segments."""
        segment1 = np.random.randn(100).astype(np.float32)
        segment2 = segment1 + np.random.randn(100).astype(np.float32) * 0.1

        cos_sim, eucl_dist = calc_feat_distance(segment1, segment2)

        # Should be highly similar
        self.assertGreater(cos_sim, 0.9)
        # But not identical
        self.assertLess(cos_sim, 1.0)


if __name__ == "__main__":
    unittest.main()
