"""Tests for core builders."""

from src.core.builders import (
    build_channel_name,
    build_user_limit_options,
    truncate_name,
)


class TestBuildChannelName:
    """Tests for build_channel_name function."""

    def test_default_template(self) -> None:
        """Test with default template."""
        result = build_channel_name("Alice")
        assert result == "Alice's Channel"

    def test_custom_template(self) -> None:
        """Test with custom template."""
        result = build_channel_name("Bob", template="VC: {name}")
        assert result == "VC: Bob"

    def test_template_without_placeholder(self) -> None:
        """Test template without {name} placeholder."""
        result = build_channel_name("Charlie", template="Static Name")
        assert result == "Static Name"


class TestBuildUserLimitOptions:
    """Tests for build_user_limit_options function."""

    def test_returns_list_of_tuples(self) -> None:
        """Test that it returns a list of tuples."""
        options = build_user_limit_options()
        assert isinstance(options, list)
        assert all(isinstance(opt, tuple) for opt in options)
        assert all(len(opt) == 2 for opt in options)

    def test_first_option_is_no_limit(self) -> None:
        """Test that the first option is no limit (0)."""
        options = build_user_limit_options()
        assert options[0] == ("No Limit", 0)

    def test_all_values_are_valid(self) -> None:
        """Test that all values are valid user limits."""
        options = build_user_limit_options()
        for _, value in options:
            assert 0 <= value <= 99


class TestTruncateName:
    """Tests for truncate_name function."""

    def test_short_name_unchanged(self) -> None:
        """Test that short names are unchanged."""
        result = truncate_name("Short Name")
        assert result == "Short Name"

    def test_exact_length_unchanged(self) -> None:
        """Test that names at exact limit are unchanged."""
        name = "a" * 100
        result = truncate_name(name, max_length=100)
        assert result == name

    def test_long_name_truncated(self) -> None:
        """Test that long names are truncated."""
        name = "a" * 110
        result = truncate_name(name, max_length=100)
        assert len(result) == 100
        assert result.endswith("...")

    def test_custom_max_length(self) -> None:
        """Test with custom max length."""
        name = "This is a long name"
        result = truncate_name(name, max_length=10)
        assert len(result) == 10
        assert result == "This is..."
