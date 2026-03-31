"""Tests for silence detection functionality."""

from pathlib import Path
import unittest
import tempfile
import subprocess
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.files.audio import find_silent_segments, get_duration
from tests.audio.audio_test_helpers import download_test_audio


class TestGetSilentSegments(unittest.TestCase):
    """Test cases for find_silent_segments function."""

    @classmethod
    def setUpClass(cls):
        """Ensure test audio file is downloaded."""
        cls.test_audio = download_test_audio()
        cls.audio_duration = get_duration(cls.test_audio)

    def test_get_silence_segments(self):
        """Test getting silence segments from audio."""
        silence_segments = find_silent_segments(self.test_audio)

        self.assertIsInstance(silence_segments, list)
        # Should have at least some silence segments
        self.assertGreater(len(silence_segments), 0)
        # All segments should be tuples of (start, end)
        for seg in silence_segments:
            self.assertIsInstance(seg, tuple)
            self.assertEqual(len(seg), 2)
            self.assertIsInstance(seg[0], float)
            self.assertIsInstance(seg[1], float)

    def test_silence_segments_sorted(self):
        """Test that silence segments are in chronological order."""
        silence_segments = find_silent_segments(self.test_audio)

        if len(silence_segments) > 1:
            # Segments should be sorted by start time
            starts = [seg[0] for seg in silence_segments]
            self.assertEqual(starts, sorted(starts))

    def test_silence_segments_within_duration(self):
        """Test that all silence segments are within audio duration."""
        silence_segments = find_silent_segments(self.test_audio)

        for start, end in silence_segments:
            self.assertGreaterEqual(start, 0.0)
            self.assertGreaterEqual(end, start)
            assert self.audio_duration is not None
            self.assertLessEqual(end, self.audio_duration + 0.1)

    def test_segments_do_not_overlap(self):
        """Test that silence segments do not overlap."""
        silence_segments = find_silent_segments(self.test_audio)

        if len(silence_segments) > 1:
            for i in range(len(silence_segments) - 1):
                current_end = silence_segments[i][1]
                next_start = silence_segments[i + 1][0]
                self.assertLessEqual(current_end, next_start)

    def test_silence_segments_valid(self):
        """Test that all silence segments have valid start/end times."""
        silence_segments = find_silent_segments(self.test_audio)

        for start, end in silence_segments:
            self.assertIsInstance(start, float)
            self.assertIsInstance(end, float)
            self.assertTrue(start >= 0.0)
            self.assertTrue(end > start)


class TestGetSilentSegmentsSynthetic(unittest.TestCase):
    """Test find_silent_segments with synthetic audio."""

    def test_silence_with_synthetic_audio(self):
        """Test silence detection with synthetic audio containing silence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_file = Path(tmp_dir) / "test_with_silence.mp3"

            # Create audio with explicit silence: 1s tone, 2s silence, 1s tone
            cmd = [
                "ffmpeg",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=1",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=duration=2",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=1",
                "-filter_complex",
                "[0:a][1:a][2:a]concat=n=3:v=0:a=1",
                "-acodec",
                "libmp3lame",
                "-y",
                str(test_file),
            ]
            subprocess.run(cmd, check=True, capture_output=True)

            silence_segments = find_silent_segments(test_file)

            # Should detect silence in the middle (around 1s-3s)
            self.assertIsInstance(silence_segments, list)
            self.assertGreater(len(silence_segments), 0)
            # First segment should start around 1.0s (after first tone)
            if len(silence_segments) > 0:
                self.assertGreater(silence_segments[0][0], 0.5)
                self.assertLess(silence_segments[0][0], 1.5)

    def test_silence_with_no_silence(self):
        """Test silence detection with continuous audio (no silence)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_file = Path(tmp_dir) / "test_no_silence.mp3"

            # Create continuous tone
            cmd = [
                "ffmpeg",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=5",
                "-acodec",
                "libmp3lame",
                "-y",
                str(test_file),
            ]
            subprocess.run(cmd, check=True, capture_output=True)

            silence_segments = find_silent_segments(test_file)

            # Continuous tone may have minimal silence detected
            self.assertIsInstance(silence_segments, list)

    def test_silence_with_all_silence(self):
        """Test silence detection with completely silent audio."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_file = Path(tmp_dir) / "test_all_silence.mp3"

            # Create silent audio
            cmd = [
                "ffmpeg",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=duration=5",
                "-acodec",
                "libmp3lame",
                "-y",
                str(test_file),
            ]
            subprocess.run(cmd, check=True, capture_output=True)

            silence_segments = find_silent_segments(test_file)

            # Should detect silence throughout (entire file is silent)
            self.assertIsInstance(silence_segments, list)
            self.assertGreater(len(silence_segments), 0)
            # Should have one segment covering most/all of the duration
            if len(silence_segments) > 0:
                total_silence = sum(end - start for start, end in silence_segments)
                self.assertGreater(
                    total_silence, 4.0
                )  # Most of the 5s should be silent


class TestGetSilentSegmentsErrors(unittest.TestCase):
    """Test error cases for find_silent_segments."""

    def test_nonexistent_file(self):
        """Test that nonexistent file raises assertion error."""
        fake_file = Path("/fake/path/nonexistent.mp3")

        with self.assertRaises(AssertionError):
            find_silent_segments(fake_file)


if __name__ == "__main__":
    unittest.main()
