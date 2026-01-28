"""Tests for main entry point."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch


class TestMain:
    """Tests for main() function."""

    @patch("src.main.EphemeralVCBot")
    @patch("src.main.settings")
    async def test_starts_bot_with_token(
        self, mock_settings: AsyncMock, mock_bot_class: AsyncMock
    ) -> None:
        """Bot が discord_token で起動される。"""
        from src.main import main

        mock_settings.discord_token = "test-token-123"
        mock_bot = AsyncMock()
        mock_bot_class.return_value = mock_bot

        await main()

        mock_bot.start.assert_awaited_once_with("test-token-123")
