import unittest

from adrift.core.util.text import create_slug, is_slug, normalize_text, remove_file_extension


class TestCreateSlug(unittest.TestCase):
    """Test cases for the create_slug function."""

    def test_basic_slug(self):
        """Test basic string to slug conversion."""
        assert create_slug("Hello World") == "hello-world"
        assert create_slug("Test Title") == "test-title"

    def test_apostrophes_and_contractions(self):
        """Test handling of apostrophes and contractions."""
        assert create_slug("Don't Stop") == "dont-stop"
        assert create_slug("You're Welcome") == "youre-welcome"
        assert create_slug("I'll Be There") == "ill-be-there"
        assert create_slug("I've Got This") == "ive-got-this"
        assert create_slug("He'd Rather Not") == "hed-rather-not"
        assert create_slug("Let's Go") == "lets-go"

    def test_possessives(self):
        """Test handling of possessive forms."""
        assert create_slug("America's History") == "americas-history"
        assert create_slug("John's Book") == "johns-book"
        assert create_slug("The Cat's Meow") == "the-cats-meow"

    def test_underscores_to_apostrophes(self):
        """Test underscore to apostrophe conversion."""
        assert create_slug("America_s History") == "americas-history"
        assert create_slug("Let_s Go") == "lets-go"

    def test_special_characters(self):
        """Test removal of special characters."""
        assert create_slug("Hello@World!") == "helloworld"
        assert create_slug("Test#Title$Here") == "testtitlehere"
        assert create_slug("Price: $99.99") == "price-9999"
        assert create_slug("50% Off") == "50-off"

    def test_unicode_characters(self):
        """Test handling of non-English characters."""
        assert create_slug("Café") == "cafe"
        assert create_slug("Jalapeño") == "jalapeno"
        assert create_slug("München") == "munchen"
        assert create_slug("日本") == "ri-ben"  # Japanese characters
        assert create_slug("Привет") == "privet"  # Russian

    def test_multiple_spaces_and_hyphens(self):
        """Test normalization of spaces and hyphens."""
        assert create_slug("Hello    World") == "hello-world"
        assert create_slug("Test---Title") == "test-title"
        assert create_slug("Multiple   Spaces  Here") == "multiple-spaces-here"

    def test_leading_trailing_hyphens(self):
        """Test removal of leading and trailing hyphens."""
        assert create_slug("-Leading Hyphen") == "leading-hyphen"
        assert create_slug("Trailing Hyphen-") == "trailing-hyphen"
        assert create_slug("--Both--") == "both"

    def test_numbers(self):
        """Test handling of numbers."""
        assert create_slug("Episode 123") == "episode-123"
        assert create_slug("2024 Review") == "2024-review"
        assert create_slug("Top 10 List") == "top-10-list"

    def test_mixed_case(self):
        """Test case conversion."""
        assert create_slug("MixedCaseTitle") == "mixedcasetitle"
        assert create_slug("UPPERCASE") == "uppercase"
        assert create_slug("lowercase") == "lowercase"

    def test_file_extensions(self):
        """Test removal of file extensions."""
        assert create_slug("video.mp4") == "video"
        assert create_slug("audio.m4a") == "audio"
        assert create_slug("document.txt") == "document"

    def test_empty_string(self):
        """Test handling of empty strings."""
        assert create_slug("") == ""
        assert create_slug("   ") == ""

    def test_only_special_characters(self):
        """Test strings with only special characters."""
        assert create_slug("@#$%") == ""
        assert create_slug("!!!") == ""

    def test_long_strings(self):
        """Test truncation of long strings."""
        long_title = "a" * 200
        result = create_slug(long_title)
        assert len(result) == 100
        assert result == "a" * 100

    def test_complex_real_world_examples(self):
        """Test complex real-world podcast/video titles."""
        assert (
            create_slug("How Beer Works | Stuff You Should Know")
            == "how-beer-works-stuff-you-should-know"
        )
        assert (
            create_slug("SYSK Selects: How Champagne Works") == "sysk-selects-how-champagne-works"
        )
        assert create_slug("Behind the Bastards: Part II") == "behind-the-bastards-part-ii"
        assert create_slug("Legal Eagle - Lawyer Reacts!") == "legal-eagle-lawyer-reacts"

    def test_underscores_in_middle(self):
        """Test underscores that aren't contractions."""
        assert create_slug("test_file_name") == "test-file-name"
        assert create_slug("some_random_text") == "some-random-text"

    def test_consecutive_underscores(self):
        """Test consecutive underscores."""
        assert create_slug("test__double") == "test-double"
        assert create_slug("multiple___underscores") == "multiple-underscores"


class TestRemoveFileExtension(unittest.TestCase):
    """Test cases for the remove_file_extension function."""

    def test_common_extensions(self):
        """Test removal of common file extensions."""
        assert remove_file_extension("video.mp4") == "video"
        assert remove_file_extension("audio.m4a") == "audio"
        assert remove_file_extension("document.txt") == "document"
        assert remove_file_extension("image.jpg") == "image"

    def test_no_extension(self):
        """Test files without extensions."""
        assert remove_file_extension("filename") == "filename"
        assert remove_file_extension("no_ext") == "no_ext"

    def test_multiple_dots(self):
        """Test files with multiple dots."""
        assert remove_file_extension("file.name.mp4") == "file.name"
        assert remove_file_extension("my.file.txt") == "my.file"

    def test_case_insensitive(self):
        """Test case-insensitive extension removal."""
        assert remove_file_extension("VIDEO.MP4") == "VIDEO"
        assert remove_file_extension("Audio.M4A") == "Audio"


class TestIsSlug(unittest.TestCase):
    """Test cases for the is_slug function."""

    def test_valid_slugs(self):
        """Test valid slug formats."""
        assert is_slug("hello-world")
        assert is_slug("test-title-here")
        assert is_slug("episode-123")
        assert is_slug("simple")

    def test_invalid_slugs(self):
        """Test invalid slug formats."""
        assert not is_slug("Hello World")  # Uppercase and space
        assert not is_slug("test_title")  # Underscore
        assert not is_slug("-leading")  # Leading hyphen
        assert not is_slug("trailing-")  # Trailing hyphen
        assert not is_slug("test--double")  # Double hyphen
        assert not is_slug("test@title")  # Special character
        assert not is_slug("")  # Empty string


class TestNormalizeTitle(unittest.TestCase):
    """Test cases for the normalize_text function."""

    def test_basic_normalization(self):
        """Test basic title normalization."""
        result = normalize_text("Hello World")
        assert result == "hello world"

    def test_punctuation_removal(self):
        """Test removal of punctuation."""
        result = normalize_text("Test: Title!")
        assert ":" not in result
        assert "!" not in result

    def test_whitespace_normalization(self):
        """Test whitespace normalization."""
        result = normalize_text("Multiple   Spaces")
        assert result == "multiple spaces"

    def test_part_conversion(self):
        """Test (Pt.) conversion to 'part'."""
        result = normalize_text("Episode (Pt. II)")
        assert "part" in result

    def test_file_extension_removal(self):
        """Test that file extensions are removed."""
        result = normalize_text("video.mp4")
        assert ".mp4" not in result


if __name__ == "__main__":
    unittest.main()
