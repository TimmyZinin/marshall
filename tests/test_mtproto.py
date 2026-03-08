"""Tests for MTProto DM transport."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.listener.transport import IncomingMessage


class TestIncomingMessageNewFields:
    """Test new fields added to IncomingMessage for DM and voice support."""

    def test_default_source_type(self):
        msg = IncomingMessage(
            chat_id=-100, chat_name="Chat", sender_id=1, sender_name="User",
            message_id=1, text="test", timestamp=1.0,
        )
        assert msg.source_type == "group_chat"
        assert msg.is_voice is False
        assert msg.audio_duration_sec == 0

    def test_dm_source_type(self):
        msg = IncomingMessage(
            chat_id=12345, chat_name="DM:Диспетчер↔Водитель", sender_id=1,
            sender_name="Водитель Иванов", message_id=2, text="Рейс 4521, выехал",
            timestamp=1.0, source_type="dm",
        )
        assert msg.source_type == "dm"

    def test_voice_transcription_source(self):
        msg = IncomingMessage(
            chat_id=12345, chat_name="DM:Диспетчер↔Водитель", sender_id=1,
            sender_name="Водитель", message_id=3, text="стою в пробке уже 30 минут",
            timestamp=1.0, source_type="voice_transcription",
            is_voice=True, audio_duration_sec=15,
        )
        assert msg.source_type == "voice_transcription"
        assert msg.is_voice is True
        assert msg.audio_duration_sec == 15


class TestMTProtoTransportInit:
    """Test MTProtoTransport initialization."""

    @pytest.mark.asyncio
    async def test_no_sessions_logs_warning(self):
        from src.listener.mtproto import MTProtoTransport
        queue = asyncio.Queue()
        transport = MTProtoTransport(
            queue=queue, api_id=12345, api_hash="abc",
            sessions=[],
        )
        # Should not raise, just log warning
        await transport.start()
        assert len(transport._clients) == 0
        await transport.stop()

    @pytest.mark.asyncio
    async def test_empty_session_string_skipped(self):
        from src.listener.mtproto import MTProtoTransport
        queue = asyncio.Queue()
        transport = MTProtoTransport(
            queue=queue, api_id=12345, api_hash="abc",
            sessions=[{"session_string": "", "dispatcher_name": "Test"}],
        )
        await transport.start()
        assert len(transport._clients) == 0
        await transport.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_clients(self):
        from src.listener.mtproto import MTProtoTransport
        queue = asyncio.Queue()
        transport = MTProtoTransport(
            queue=queue, api_id=12345, api_hash="abc",
        )
        await transport.stop()
        assert transport._clients == []


class TestMTProtoMessageFiltering:
    """Test DM vs group message filtering logic."""

    def test_dm_message_has_correct_chat_name(self):
        """DM messages should have formatted chat name."""
        msg = IncomingMessage(
            chat_id=12345, chat_name="DM:Диспетчер1↔Водитель Петров",
            sender_id=67890, sender_name="Водитель Петров",
            message_id=100, text="Рейс 4521, загрузка завершена",
            timestamp=1709800000.0, source_type="dm",
        )
        assert "DM:" in msg.chat_name
        assert "Диспетчер1" in msg.chat_name
        assert msg.source_type == "dm"

    def test_group_chat_message_preserved(self):
        """Group chat messages should keep source_type=group_chat."""
        msg = IncomingMessage(
            chat_id=-1001234567890, chat_name="Диспетчерская WB",
            sender_id=12345, sender_name="Иванов",
            message_id=200, text="Рейс 4521 в пути",
            timestamp=1709800000.0, source_type="group_chat",
        )
        assert msg.source_type == "group_chat"
