import sys
import unittest
from pathlib import Path

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.utils.text import create_slug, is_slug, normalize_text, remove_file_extension


class TestCreateSlug(unittest.TestCase):
    """Test cases for the create_slug function."""

    def test_basic_slug(self):
        """Test basic string to slug conversion."""
        self.assertEqual(create_slug("Hello World"), "hello-world")
        self.assertEqual(create_slug("Test Title"), "test-title")

    def test_apostrophes_and_contractions(self):
        """Test handling of apostrophes and contractions."""
        self.assertEqual(create_slug("Don't Stop"), "dont-stop")
        self.assertEqual(create_slug("You're Welcome"), "youre-welcome")
        self.assertEqual(create_slug("I'll Be There"), "ill-be-there")
        self.assertEqual(create_slug("I've Got This"), "ive-got-this")
        self.assertEqual(create_slug("He'd Rather Not"), "hed-rather-not")
        self.assertEqual(create_slug("Let's Go"), "lets-go")

    def test_possessives(self):
        """Test handling of possessive forms."""
        self.assertEqual(create_slug("America's History"), "americas-history")
        self.assertEqual(create_slug("John's Book"), "johns-book")
        self.assertEqual(create_slug("The Cat's Meow"), "the-cats-meow")

    def test_underscores_to_apostrophes(self):
        """Test underscore to apostrophe conversion."""
        self.assertEqual(create_slug("America_s History"), "americas-history")
        self.assertEqual(create_slug("Let_s Go"), "lets-go")

    def test_special_characters(self):
        """Test removal of special characters."""
        self.assertEqual(create_slug("Hello@World!"), "helloworld")
        self.assertEqual(create_slug("Test#Title$Here"), "testtitlehere")
        self.assertEqual(create_slug("Price: $99.99"), "price-9999")
        self.assertEqual(create_slug("50% Off"), "50-off")

    def test_unicode_characters(self):
        """Test handling of non-English characters."""
        self.assertEqual(create_slug("Café"), "cafe")
        self.assertEqual(create_slug("Jalapeño"), "jalapeno")
        self.assertEqual(create_slug("München"), "munchen")
        self.assertEqual(create_slug("日本"), "ri-ben")  # Japanese characters
        self.assertEqual(create_slug("Привет"), "privet")  # Russian

    def test_multiple_spaces_and_hyphens(self):
        """Test normalization of spaces and hyphens."""
        self.assertEqual(create_slug("Hello    World"), "hello-world")
        self.assertEqual(create_slug("Test---Title"), "test-title")
        self.assertEqual(create_slug("Multiple   Spaces  Here"), "multiple-spaces-here")

    def test_leading_trailing_hyphens(self):
        """Test removal of leading and trailing hyphens."""
        self.assertEqual(create_slug("-Leading Hyphen"), "leading-hyphen")
        self.assertEqual(create_slug("Trailing Hyphen-"), "trailing-hyphen")
        self.assertEqual(create_slug("--Both--"), "both")

    def test_numbers(self):
        """Test handling of numbers."""
        self.assertEqual(create_slug("Episode 123"), "episode-123")
        self.assertEqual(create_slug("2024 Review"), "2024-review")
        self.assertEqual(create_slug("Top 10 List"), "top-10-list")

    def test_mixed_case(self):
        """Test case conversion."""
        self.assertEqual(create_slug("MixedCaseTitle"), "mixedcasetitle")
        self.assertEqual(create_slug("UPPERCASE"), "uppercase")
        self.assertEqual(create_slug("lowercase"), "lowercase")

    def test_file_extensions(self):
        """Test removal of file extensions."""
        self.assertEqual(create_slug("video.mp4"), "video")
        self.assertEqual(create_slug("audio.m4a"), "audio")
        self.assertEqual(create_slug("document.txt"), "document")

    def test_empty_string(self):
        """Test handling of empty strings."""
        self.assertEqual(create_slug(""), "")
        self.assertEqual(create_slug("   "), "")

    def test_only_special_characters(self):
        """Test strings with only special characters."""
        self.assertEqual(create_slug("@#$%"), "")
        self.assertEqual(create_slug("!!!"), "")

    def test_long_strings(self):
        """Test truncation of long strings."""
        long_title = "a" * 200
        result = create_slug(long_title)
        self.assertEqual(len(result), 100)
        self.assertEqual(result, "a" * 100)

    def test_complex_real_world_examples(self):
        """Test complex real-world podcast/video titles."""
        self.assertEqual(
            create_slug("How Beer Works | Stuff You Should Know"),
            "how-beer-works-stuff-you-should-know",
        )
        self.assertEqual(
            create_slug("SYSK Selects: How Champagne Works"),
            "sysk-selects-how-champagne-works",
        )
        self.assertEqual(create_slug("Behind the Bastards: Part II"), "behind-the-bastards-part-ii")
        self.assertEqual(create_slug("Legal Eagle - Lawyer Reacts!"), "legal-eagle-lawyer-reacts")

    def test_underscores_in_middle(self):
        """Test underscores that aren't contractions."""
        self.assertEqual(create_slug("test_file_name"), "test-file-name")
        self.assertEqual(create_slug("some_random_text"), "some-random-text")

    def test_consecutive_underscores(self):
        """Test consecutive underscores."""
        self.assertEqual(create_slug("test__double"), "test-double")
        self.assertEqual(create_slug("multiple___underscores"), "multiple-underscores")


class TestRemoveFileExtension(unittest.TestCase):
    """Test cases for the remove_file_extension function."""

    def test_common_extensions(self):
        """Test removal of common file extensions."""
        self.assertEqual(remove_file_extension("video.mp4"), "video")
        self.assertEqual(remove_file_extension("audio.m4a"), "audio")
        self.assertEqual(remove_file_extension("document.txt"), "document")
        self.assertEqual(remove_file_extension("image.jpg"), "image")

    def test_no_extension(self):
        """Test files without extensions."""
        self.assertEqual(remove_file_extension("filename"), "filename")
        self.assertEqual(remove_file_extension("no_ext"), "no_ext")

    def test_multiple_dots(self):
        """Test files with multiple dots."""
        self.assertEqual(remove_file_extension("file.name.mp4"), "file.name")
        self.assertEqual(remove_file_extension("my.file.txt"), "my.file")

    def test_case_insensitive(self):
        """Test case-insensitive extension removal."""
        self.assertEqual(remove_file_extension("VIDEO.MP4"), "VIDEO")
        self.assertEqual(remove_file_extension("Audio.M4A"), "Audio")


class TestIsSlug(unittest.TestCase):
    """Test cases for the is_slug function."""

    def test_valid_slugs(self):
        """Test valid slug formats."""
        self.assertTrue(is_slug("hello-world"))
        self.assertTrue(is_slug("test-title-here"))
        self.assertTrue(is_slug("episode-123"))
        self.assertTrue(is_slug("simple"))

    def test_invalid_slugs(self):
        """Test invalid slug formats."""
        self.assertFalse(is_slug("Hello World"))  # Uppercase and space
        self.assertFalse(is_slug("test_title"))  # Underscore
        self.assertFalse(is_slug("-leading"))  # Leading hyphen
        self.assertFalse(is_slug("trailing-"))  # Trailing hyphen
        self.assertFalse(is_slug("test--double"))  # Double hyphen
        self.assertFalse(is_slug("test@title"))  # Special character
        self.assertFalse(is_slug(""))  # Empty string


class TestNormalizeTitle(unittest.TestCase):
    """Test cases for the normalize_text function."""

    def test_basic_normalization(self):
        """Test basic title normalization."""
        result = normalize_text("Hello World")
        self.assertEqual(result, "hello world")

    def test_punctuation_removal(self):
        """Test removal of punctuation."""
        result = normalize_text("Test: Title!")
        self.assertNotIn(":", result)
        self.assertNotIn("!", result)

    def test_whitespace_normalization(self):
        """Test whitespace normalization."""
        result = normalize_text("Multiple   Spaces")
        self.assertEqual(result, "multiple spaces")

    def test_part_conversion(self):
        """Test (Pt.) conversion to 'part'."""
        result = normalize_text("Episode (Pt. II)")
        self.assertIn("part", result)

    def test_file_extension_removal(self):
        """Test that file extensions are removed."""
        result = normalize_text("video.mp4")
        self.assertNotIn(".mp4", result)


if __name__ == "__main__":
    unittest.main()
