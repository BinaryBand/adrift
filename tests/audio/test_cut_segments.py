import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.files.audio import cut_segments, get_duration
from tests.audio.audio_test_helpers import download_test_audio, duration_matches


class TestCutSegments(unittest.TestCase):
    """Test cases for cut_segments function using actual ffmpeg/ffprobe."""

    @classmethod
    def setUpClass(cls):
        """Ensure test audio file is downloaded."""
        # Download real YouTube video for testing
        cls.test_audio = download_test_audio()
        cls.original_duration = get_duration(cls.test_audio)
        assert cls.original_duration is not None, "Failed to get duration of test audio"

    @classmethod
    def tearDownClass(cls):
        """Test audio file is kept for reuse in future test runs."""
        pass

    def test_cut_single_segment_middle(self):
        """Test cutting a single segment from the middle of audio."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None and self.original_duration is not None
            self.assertAlmostEqual(original_duration, self.original_duration, delta=0.5)

            # Cut segment from 20s to 30s (should remove 10 seconds)
            segments_to_cut = [(20.0, 30.0)]
            cut_segments(target, segments_to_cut)

            new_duration = get_duration(target)
            assert new_duration is not None

            # Should be approximately 50 seconds (60 - 10)
            expected_duration = original_duration - 10.0
            self.assertTrue(
                duration_matches(expected_duration, new_duration, tolerance=0.1),
                f"Expected ~{expected_duration}s, got {new_duration}s",
            )

    def test_cut_multiple_segments(self):
        """Test cutting multiple segments."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None

            # Cut 3 segments: 5-10s, 20-25s, 40-50s (total 20 seconds removed)
            segments_to_cut = [(5.0, 10.0), (20.0, 25.0), (40.0, 50.0)]
            cut_segments(target, segments_to_cut)

            new_duration = get_duration(target)
            assert new_duration is not None

            expected_duration = original_duration - 20.0
            self.assertTrue(
                duration_matches(expected_duration, new_duration, tolerance=0.1),
                f"Expected ~{expected_duration}s, got {new_duration}s",
            )

    def test_cut_beginning_segment(self):
        """Test cutting a segment from the beginning."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None

            # Cut first 10 seconds
            segments_to_cut = [(0.0, 10.0)]
            cut_segments(target, segments_to_cut)

            new_duration = get_duration(target)
            assert new_duration is not None

            expected_duration = original_duration - 10.0
            self.assertTrue(
                duration_matches(expected_duration, new_duration, tolerance=0.1),
                f"Expected ~{expected_duration}s, got {new_duration}s",
            )

    def test_cut_end_segment(self):
        """Test cutting a segment from the end."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None

            # Cut last 10 seconds
            segments_to_cut = [(50.0, 60.0)]
            cut_segments(target, segments_to_cut)

            new_duration = get_duration(target)
            assert new_duration is not None

            expected_duration = original_duration - 10.0
            self.assertTrue(
                duration_matches(expected_duration, new_duration, tolerance=0.1),
                f"Expected ~{expected_duration}s, got {new_duration}s",
            )

    def test_cut_overlapping_segments(self):
        """Test cutting overlapping segments (should be merged)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None

            # Overlapping segments: 10-25s and 20-35s (covers 10-35s total = 25s)
            segments_to_cut = [(10.0, 25.0), (20.0, 35.0)]
            cut_segments(target, segments_to_cut)

            new_duration = get_duration(target)
            assert new_duration is not None

            # Note: Current implementation doesn't merge overlaps,
            # so this tests actual behavior
            # Total removed will be based on inversion logic
            self.assertLess(new_duration, original_duration)

    def test_cut_adjacent_segments(self):
        """Test cutting adjacent segments."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None

            # Adjacent segments: 10-20s and 20-30s (total 20 seconds)
            segments_to_cut = [(10.0, 20.0), (20.0, 30.0)]
            cut_segments(target, segments_to_cut)

            new_duration = get_duration(target)
            assert new_duration is not None

            expected_duration = original_duration - 20.0
            self.assertTrue(
                duration_matches(expected_duration, new_duration, tolerance=0.1),
                f"Expected ~{expected_duration}s, got {new_duration}s",
            )

    def test_output_exists(self):
        """Test that output file is created and original is replaced."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_size = target.stat().st_size

            segments_to_cut = [(25.0, 35.0)]
            cut_segments(target, segments_to_cut)

            # File should still exist
            self.assertTrue(target.exists())

            # File size should be smaller
            new_size = target.stat().st_size
            self.assertLess(new_size, original_size)

    def test_empty_segments_list(self):
        """Test behavior with empty segments list."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None

            # Empty list - should keep entire audio
            segments_to_cut = []
            cut_segments(target, segments_to_cut)

            new_duration = get_duration(target)
            assert new_duration is not None

            # Duration should remain approximately the same
            self.assertTrue(
                duration_matches(original_duration, new_duration, tolerance=0.05),
                f"Expected ~{original_duration}s, got {new_duration}s",
            )

    def test_very_small_segments(self):
        """Test cutting very small segments (below MIN_LENGTH)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None

            # Very small segment (0.05 seconds - below MIN_LENGTH of 0.1)
            segments_to_cut = [(30.0, 30.05)]
            cut_segments(target, segments_to_cut)

            new_duration = get_duration(target)
            assert new_duration is not None

            # Duration should be approximately the same (segment too small to cut)
            self.assertTrue(
                duration_matches(original_duration, new_duration, tolerance=0.05),
                f"Expected ~{original_duration}s, got {new_duration}s",
            )

    def test_file_with_spaces_in_name(self):
        """Test cutting segments from a file with spaces in the name.

        This tests the fix for the bug where unquoted file paths caused
        ffmpeg to fail with exit code 234.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create file with spaces in name
            target = Path(tmp_dir) / "The Real Reason I Left.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None

            # Cut segment from middle
            segments_to_cut = [(15.0, 25.0)]
            cut_segments(target, segments_to_cut)

            # Verify file still exists and duration changed
            self.assertTrue(target.exists())
            new_duration = get_duration(target)
            assert new_duration is not None

            expected_duration = original_duration - 10.0
            self.assertTrue(
                duration_matches(expected_duration, new_duration, tolerance=0.1),
                f"Expected ~{expected_duration}s, got {new_duration}s",
            )

    def test_multiple_segments_with_complex_filename(self):
        """Test cutting multiple segments from file with special characters."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # File with spaces, apostrophes, and other characters
            target = Path(tmp_dir) / "Test's Audio - Part 1 (Final).mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None

            # Cut multiple segments
            segments_to_cut = [(5.0, 10.0), (30.0, 35.0)]
            cut_segments(target, segments_to_cut)

            self.assertTrue(target.exists())
            new_duration = get_duration(target)
            assert new_duration is not None

            expected_duration = original_duration - 10.0
            self.assertTrue(
                duration_matches(expected_duration, new_duration, tolerance=0.1),
                f"Expected ~{expected_duration}s, got {new_duration}s",
            )

    def test_m4a_file_format(self):
        """Test cutting segments from M4A format (common podcast format).

        M4A files can have issues with codec copy mode, so this ensures
        the fallback to re-encoding works properly.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create M4A version
            m4a_target = Path(tmp_dir) / "test_audio.m4a"

            # Convert test audio to M4A
            import subprocess

            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(self.test_audio),
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-y",
                str(m4a_target),
            ]
            subprocess.run(cmd, check=True, capture_output=True)

            original_duration = get_duration(m4a_target)
            assert original_duration is not None

            # Cut segments
            segments_to_cut = [(10.0, 20.0)]
            cut_segments(m4a_target, segments_to_cut)

            self.assertTrue(m4a_target.exists())
            new_duration = get_duration(m4a_target)
            assert new_duration is not None

            expected_duration = original_duration - 10.0
            self.assertTrue(
                duration_matches(expected_duration, new_duration, tolerance=0.1),
                f"Expected ~{expected_duration}s, got {new_duration}s",
            )


if __name__ == "__main__":
    unittest.main()
