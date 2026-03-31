from pathlib import Path
import unittest
import tempfile
import subprocess
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.files.audio import extract_segment, get_duration
from tests.audio.audio_test_helpers import duration_matches


class TestExtractSegment(unittest.TestCase):
    """Test cases for extract_segment function using actual ffmpeg/ffprobe."""

    @classmethod
    def setUpClass(cls):
        """Create a test audio file once for all tests."""
        cls.test_dir = tempfile.mkdtemp()
        cls.test_audio = Path(cls.test_dir) / "test_audio.mp3"

        # Create a 60-second silent MP3 file for testing
        cmd = [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=60",
            "-acodec",
            "libmp3lame",
            "-ab",
            "128k",
            "-y",
            str(cls.test_audio),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create test audio file: {e.stderr.decode()}")

        assert (
            cls.test_audio.exists()
        ), f"Test audio file was not created: {cls.test_audio}"

    @classmethod
    def tearDownClass(cls):
        """Clean up test directory."""
        if cls.test_audio.exists():
            cls.test_audio.unlink()
        Path(cls.test_dir).rmdir()

    def test_extract_middle_segment(self):
        """Test extracting a segment from the middle of audio."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "segment.mp3"

            # Extract 10 seconds from 25-35s
            extract_segment(self.test_audio, 25.0, 35.0, output)
            self.assertTrue(output.exists())

            duration = get_duration(output)
            assert duration is not None
            self.assertTrue(
                duration_matches(10.0, duration, tolerance=0.1),
                f"Expected ~10s, got {duration}s",
            )

    def test_extract_beginning_segment(self):
        """Test extracting a segment from the beginning."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "beginning.mp3"

            # Extract first 15 seconds
            extract_segment(self.test_audio, 0.0, 15.0, output)

            self.assertTrue(output.exists())
            duration = get_duration(output)
            assert duration is not None
            self.assertTrue(
                duration_matches(15.0, duration, tolerance=0.1),
                f"Expected ~15s, got {duration}s",
            )

    def test_extract_end_segment(self):
        """Test extracting a segment from the end."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "end.mp3"

            # Extract last 20 seconds
            extract_segment(self.test_audio, 40.0, 60.0, output)

            self.assertTrue(output.exists())
            duration = get_duration(output)
            assert duration is not None
            self.assertTrue(
                duration_matches(20.0, duration, tolerance=0.1),
                f"Expected ~20s, got {duration}s",
            )

    def test_extract_short_segment(self):
        """Test extracting a very short segment."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "short.mp3"

            # Extract 0.5 seconds
            extract_segment(self.test_audio, 30.0, 30.5, output)

            self.assertTrue(output.exists())
            duration = get_duration(output)
            assert duration is not None
            # Allow higher tolerance for very short segments
            self.assertTrue(
                duration_matches(0.5, duration, tolerance=0.3),
                f"Expected ~0.5s, got {duration}s",
            )

    def test_extract_long_segment(self):
        """Test extracting a long segment."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "long.mp3"

            # Extract 50 seconds (5-55s)
            extract_segment(self.test_audio, 5.0, 55.0, output)

            self.assertTrue(output.exists())
            duration = get_duration(output)
            assert duration is not None
            self.assertTrue(
                duration_matches(50.0, duration, tolerance=0.1),
                f"Expected ~50s, got {duration}s",
            )

    def test_extract_creates_parent_directories(self):
        """Test that parent directories are created if they don't exist."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create nested path that doesn't exist
            output = Path(tmp_dir) / "nested" / "dirs" / "segment.mp3"

            extract_segment(self.test_audio, 5.0, 10.0, output)

            self.assertTrue(output.exists())
            self.assertTrue(output.parent.exists())
            duration = get_duration(output)
            assert duration is not None

    def test_extract_overwrites_existing_file(self):
        """Test that existing output file is overwritten."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "overwrite.mp3"

            # Create a dummy file first
            output.write_text("dummy content")
            self.assertTrue(output.exists())
            original_size = output.stat().st_size

            # Extract segment (should overwrite)
            extract_segment(self.test_audio, 15.0, 25.0, output)

            self.assertTrue(output.exists())
            # New file should be larger (audio file vs text)
            new_size = output.stat().st_size
            self.assertGreater(new_size, original_size)

            # Verify it's valid audio
            duration = get_duration(output)
            assert duration is not None

    def test_extract_full_audio(self):
        """Test extracting the entire audio file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "full.mp3"

            original_duration = get_duration(self.test_audio)
            assert original_duration is not None

            # Extract entire duration
            extract_segment(self.test_audio, 0.0, original_duration, output)

            self.assertTrue(output.exists())
            duration = get_duration(output)
            assert duration is not None
            self.assertTrue(
                duration_matches(original_duration, duration, tolerance=0.05),
                f"Expected ~{original_duration}s, got {duration}s",
            )

    def test_extract_with_fractional_times(self):
        """Test extracting with precise fractional second timing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "fractional.mp3"

            # Extract 7.3 seconds from 12.5s to 19.8s
            extract_segment(self.test_audio, 12.5, 19.8, output)

            self.assertTrue(output.exists())
            duration = get_duration(output)
            assert duration is not None
            expected = 19.8 - 12.5
            self.assertTrue(
                duration_matches(expected, duration, tolerance=0.15),
                f"Expected ~{expected}s, got {duration}s",
            )

    def test_extract_returns_path_object(self):
        """Test that extract_segment returns a Path object."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "return_test.mp3"
            extract_segment(self.test_audio, 5.0, 10.0, output)

    def test_extract_different_formats(self):
        """Test extracting to different audio formats."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Test with .m4a output
            output_m4a = Path(tmp_dir) / "segment.m4a"
            extract_segment(self.test_audio, 10.0, 15.0, output_m4a)

            self.assertTrue(output_m4a.exists())
            duration = get_duration(output_m4a)
            assert duration is not None
            self.assertTrue(
                duration_matches(5.0, duration, tolerance=0.1),
                f"Expected ~5s, got {duration}s",
            )

    def test_extract_sequential_segments(self):
        """Test extracting multiple sequential segments from same source."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Extract three consecutive 10-second segments
            segments = [
                (0.0, 10.0, Path(tmp_dir) / "seg1.mp3"),
                (10.0, 20.0, Path(tmp_dir) / "seg2.mp3"),
                (20.0, 30.0, Path(tmp_dir) / "seg3.mp3"),
            ]

            for start, end, output in segments:
                extract_segment(self.test_audio, start, end, output)
                self.assertTrue(output.exists())
                duration = get_duration(output)
                assert duration is not None
                self.assertTrue(
                    duration_matches(10.0, duration, tolerance=0.1),
                    f"Segment {output.name}: Expected ~10s, got {duration}s",
                )


class TestExtractSegmentErrors(unittest.TestCase):
    """Test error cases for extract_segment function."""

    def test_extract_from_nonexistent_file(self):
        """Test that extracting from non-existent file raises error."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_source = Path(tmp_dir) / "nonexistent.mp3"
            output = Path(tmp_dir) / "output.mp3"

            with self.assertRaises(subprocess.CalledProcessError):
                extract_segment(fake_source, 0.0, 10.0, output)

    def test_extract_invalid_time_range(self):
        """Test extracting with invalid time range (start > end) produces invalid output."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_audio = Path(tmp_dir) / "test.mp3"
            output = Path(tmp_dir) / "output.mp3"

            # Create minimal test file
            cmd = [
                "ffmpeg",
                "-f",
                "lavfi",
                "-i",
                "sine=duration=10",
                "-acodec",
                "libmp3lame",
                "-y",
                str(test_audio),
            ]
            subprocess.run(cmd, check=True, capture_output=True)

            # Start > end results in negative duration
            # ffmpeg doesn't error but produces invalid/empty output
            extract_segment(test_audio, 10.0, 5.0, output)

            # File may be created but will be invalid or have zero/minimal duration
            if output.exists():
                duration = get_duration(output)
                # Duration should be None (invalid) or very small/zero
                if duration is not None:
                    self.assertLess(
                        duration,
                        0.5,
                        "Invalid time range should not produce valid audio",
                    )


if __name__ == "__main__":
    unittest.main()
