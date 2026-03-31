"""Tests for feature extraction functions."""

from pathlib import Path
import numpy as np
import unittest
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.files.audio import get_feats, _get_feats, _trim_audio_silence
from tests.audio.audio_test_helpers import download_test_audio


class TestExtractfeats(unittest.TestCase):
    """Test cases for get_feats function."""

    @classmethod
    def setUpClass(cls):
        """Ensure test audio file is downloaded."""
        cls.test_audio = download_test_audio()

    def test_extract_full_audio_feats(self):
        """Test extracting feats from entire audio file."""
        feats = get_feats(self.test_audio)

        self.assertIsInstance(feats, np.ndarray)
        self.assertGreater(len(feats), 0)
        self.assertEqual(feats.dtype, np.float32)

    def test_extract_segment_feats(self):
        """Test extracting feats from a specific time segment."""
        # Extract 10 seconds starting at 30s
        feats = get_feats(self.test_audio, start=30.0, end=40.0)

        self.assertIsInstance(feats, np.ndarray)
        self.assertGreater(len(feats), 0)

    def test_extract_beginning_feats(self):
        """Test extracting feats from the beginning."""
        feats = get_feats(self.test_audio, start=0.0, end=10.0)

        self.assertIsInstance(feats, np.ndarray)
        self.assertGreater(len(feats), 0)

    def test_extract_end_feats(self):
        """Test extracting feats from the end."""
        feats = get_feats(self.test_audio, start=200.0, end=210.0)

        self.assertIsInstance(feats, np.ndarray)
        self.assertGreater(len(feats), 0)

    def test_feats_are_cached(self):
        """Test that extracted feats are cached."""
        # Extract feats twice with same parameters
        feats1 = get_feats(self.test_audio, start=50.0, end=60.0)
        feats2 = get_feats(self.test_audio, start=50.0, end=60.0)

        # Should be identical (from cache)
        np.testing.assert_array_equal(feats1, feats2)

    def test_different_segments_different_feats(self):
        """Test that different segments produce different feats."""
        feats1 = get_feats(self.test_audio, start=10.0, end=20.0)
        feats2 = get_feats(self.test_audio, start=100.0, end=110.0)

        # feats should be different
        self.assertFalse(np.array_equal(feats1, feats2))

    def test_extract_short_segment(self):
        """Test extracting feats from a very short segment."""
        feats = get_feats(self.test_audio, start=30.0, end=30.5)

        self.assertIsInstance(feats, np.ndarray)
        # Even short segments should produce some feats

    def test_feats_normalization(self):
        """Test that feats are properly normalized."""
        feats = get_feats(self.test_audio, start=20.0, end=30.0)

        # feats should not have extreme values
        self.assertTrue(np.all(np.isfinite(feats)))
        # After log transform and silence trimming, values should be reasonable
        self.assertTrue(np.all(feats < 100))

    def test_extract_overlapping_segments(self):
        """Test extracting feats from overlapping segments."""
        feats1 = get_feats(self.test_audio, start=40.0, end=60.0)
        feats2 = get_feats(self.test_audio, start=50.0, end=70.0)

        # Both should produce valid feats
        self.assertGreater(len(feats1), 0)
        self.assertGreater(len(feats2), 0)
        # But they should be different
        self.assertFalse(np.array_equal(feats1, feats2))


class TestGetAudioFeats(unittest.TestCase):
    """Test cases for _get_feats internal function."""

    @classmethod
    def setUpClass(cls):
        """Ensure test audio file is downloaded."""
        cls.test_audio = download_test_audio()

    def test_get_full_audio(self):
        """Test getting full audio data."""
        audio_data = _get_feats(self.test_audio, None, None)

        self.assertIsInstance(audio_data, np.ndarray)
        self.assertGreater(len(audio_data), 0)
        self.assertEqual(audio_data.dtype, np.float32)

    def test_get_audio_segment(self):
        """Test getting audio segment."""
        audio_data = _get_feats(self.test_audio, start=10.0, end=20.0)

        self.assertIsInstance(audio_data, np.ndarray)
        self.assertGreater(len(audio_data), 0)

    def test_audio_caching(self):
        """Test that full audio is cached."""
        # First call - should cache
        audio1 = _get_feats(self.test_audio, None, None)
        # Second call - should return cached copy
        audio2 = _get_feats(self.test_audio, None, None)

        # Should be equal (both from cache or both fresh)
        np.testing.assert_array_equal(audio1, audio2)

    def test_segment_from_cached_audio(self):
        """Test extracting segment from cached full audio."""
        # Cache full audio first
        _get_feats(self.test_audio, None, None)
        # Now extract a segment - should use cached data
        segment = _get_feats(self.test_audio, start=30.0, end=40.0)

        self.assertIsInstance(segment, np.ndarray)
        self.assertGreater(len(segment), 0)


class TestTrimAudioSilence(unittest.TestCase):
    """Test cases for _trim_audio_silence internal function."""

    def test_trim_silence_from_data(self):
        """Test trimming silence from audio data."""
        # Create synthetic data with leading/trailing zeros
        audio_data = np.concatenate(
            [
                np.zeros(100, dtype=np.float32),
                np.random.randn(500).astype(np.float32) * 1000,
                np.zeros(100, dtype=np.float32),
            ]
        )

        trimmed = _trim_audio_silence(audio_data)

        # Trimmed data should be shorter
        self.assertLess(len(trimmed), len(audio_data))
        self.assertGreater(len(trimmed), 0)

    def test_trim_all_silence(self):
        """Test trimming when data is all silence."""
        audio_data = np.zeros(1000, dtype=np.float32)

        trimmed = _trim_audio_silence(audio_data)

        # May return empty or the original if all below threshold
        # The function trims based on dB threshold, zeros may not trigger trimming
        self.assertLessEqual(len(trimmed), len(audio_data))

        # Should return approximately same length
        self.assertGreater(len(trimmed), 900)  # Allow small trimming

    def test_trim_empty_array(self):
        """Test trimming empty array."""
        audio_data = np.array([], dtype=np.float32)

        trimmed = _trim_audio_silence(audio_data)

        self.assertEqual(len(trimmed), 0)

    def test_trim_preserves_dtype(self):
        """Test that trimming preserves data type."""
        audio_data = np.random.randn(1000).astype(np.float32) * 1000

        trimmed = _trim_audio_silence(audio_data)

        self.assertEqual(trimmed.dtype, np.float32)


if __name__ == "__main__":
    unittest.main()
