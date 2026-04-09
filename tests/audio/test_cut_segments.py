import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.files.audio import cut_segments, get_duration
from tests.audio.audio_test_helpers import download_test_audio, duration_matches


@pytest.mark.slow
class TestCutSegments(unittest.TestCase):
    """Test cases for cut_segments function using actual ffmpeg/ffprobe."""

    @classmethod
    def setUpClass(cls):
        cls.test_audio = download_test_audio()
        cls.original_duration = get_duration(cls.test_audio)
        assert cls.original_duration is not None, "Failed to get duration of test audio"

    def test_cut_single_segment_middle(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None
            cut_segments(target, [(20.0, 30.0)])

            new_duration = get_duration(target)
            assert new_duration is not None
            self.assertTrue(
                duration_matches(original_duration - 10.0, new_duration, tolerance=0.1),
                f"Expected ~{original_duration - 10.0}s, got {new_duration}s",
            )

    def test_cut_multiple_segments(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None
            cut_segments(target, [(5.0, 10.0), (20.0, 25.0), (40.0, 50.0)])

            new_duration = get_duration(target)
            assert new_duration is not None
            self.assertTrue(
                duration_matches(original_duration - 20.0, new_duration, tolerance=0.1),
                f"Expected ~{original_duration - 20.0}s, got {new_duration}s",
            )

    def test_cut_beginning_segment(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None
            cut_segments(target, [(0.0, 10.0)])

            new_duration = get_duration(target)
            assert new_duration is not None
            self.assertTrue(
                duration_matches(original_duration - 10.0, new_duration, tolerance=0.1),
                f"Expected ~{original_duration - 10.0}s, got {new_duration}s",
            )

    def test_cut_end_segment(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None
            cut_segments(target, [(50.0, 60.0)])

            new_duration = get_duration(target)
            assert new_duration is not None
            self.assertTrue(
                duration_matches(original_duration - 10.0, new_duration, tolerance=0.1),
                f"Expected ~{original_duration - 10.0}s, got {new_duration}s",
            )

    def test_cut_overlapping_segments(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None
            cut_segments(target, [(10.0, 25.0), (20.0, 35.0)])

            new_duration = get_duration(target)
            assert new_duration is not None
            self.assertLess(new_duration, original_duration)

    def test_cut_adjacent_segments(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None
            cut_segments(target, [(10.0, 20.0), (20.0, 30.0)])

            new_duration = get_duration(target)
            assert new_duration is not None
            self.assertTrue(
                duration_matches(original_duration - 20.0, new_duration, tolerance=0.1),
                f"Expected ~{original_duration - 20.0}s, got {new_duration}s",
            )

    def test_output_exists(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())
            original_size = target.stat().st_size
            cut_segments(target, [(25.0, 35.0)])
            self.assertTrue(target.exists())
            self.assertLess(target.stat().st_size, original_size)

    def test_empty_segments_list(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None
            cut_segments(target, [])

            new_duration = get_duration(target)
            assert new_duration is not None
            self.assertTrue(
                duration_matches(original_duration, new_duration, tolerance=0.05),
                f"Expected ~{original_duration}s, got {new_duration}s",
            )

    def test_very_small_segments(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output.mp3"
            target.write_bytes(self.test_audio.read_bytes())

            original_duration = get_duration(target)
            assert original_duration is not None
            # Segment below MIN_LENGTH — should be skipped, no duration change
            cut_segments(target, [(30.0, 30.05)])

            new_duration = get_duration(target)
            assert new_duration is not None
            self.assertTrue(
                duration_matches(original_duration, new_duration, tolerance=0.05),
                f"Expected ~{original_duration}s, got {new_duration}s",
            )

    def test_special_character_filenames(self):
        """Filenames with spaces, apostrophes, and parentheses must not break ffmpeg."""
        filenames = [
            "The Real Reason I Left.mp3",
            "Test's Audio - Part 1 (Final).mp3",
        ]
        for filename in filenames:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp_dir:
                target = Path(tmp_dir) / filename
                target.write_bytes(self.test_audio.read_bytes())

                original_duration = get_duration(target)
                assert original_duration is not None
                cut_segments(target, [(15.0, 25.0)])

                self.assertTrue(target.exists())
                new_duration = get_duration(target)
                assert new_duration is not None
                self.assertTrue(
                    duration_matches(original_duration - 10.0, new_duration, tolerance=0.1),
                    f"Expected ~{original_duration - 10.0}s, got {new_duration}s",
                )

    def test_m4a_file_format(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            m4a_target = Path(tmp_dir) / "test_audio.m4a"
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
            cut_segments(m4a_target, [(10.0, 20.0)])

            self.assertTrue(m4a_target.exists())
            new_duration = get_duration(m4a_target)
            assert new_duration is not None
            self.assertTrue(
                duration_matches(original_duration - 10.0, new_duration, tolerance=0.1),
                f"Expected ~{original_duration - 10.0}s, got {new_duration}s",
            )


if __name__ == "__main__":
    unittest.main()
