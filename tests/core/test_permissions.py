"""Tests for core permissions."""

from src.core.permissions import is_owner


class TestIsOwner:
    """Tests for is_owner function."""

    def test_owner_matches(self) -> None:
        """Test when user is the owner."""
        assert is_owner("123456789", 123456789) is True

    def test_owner_does_not_match(self) -> None:
        """Test when user is not the owner."""
        assert is_owner("123456789", 987654321) is False

    def test_owner_id_as_string(self) -> None:
        """Test that owner_id is correctly compared as string."""
        assert is_owner("123", 123) is True
        assert is_owner("0123", 123) is False
