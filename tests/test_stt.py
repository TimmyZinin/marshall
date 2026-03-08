"""Tests for Speech-to-Text transcription module."""
import json
import os
import pytest
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from src.stt.transcriber import Transcriber
from src.listener.voice_handler import VoiceHandler, MAX_AUDIO_DURATION_SEC
from src.listener.transport import IncomingMessage


class TestTranscriberInit:
    """Test Transcriber initialization and configuration."""

    def test_init_with_groq_key(self):
        t = Transcriber(groq_api_key="test-key")
        assert t._groq_key == "test-key"

    def test_init_without_keys(self):
        t = Transcriber()
        assert t._groq_key is None

    @pytest.mark.asyncio
    async def test_no_backend_raises(self):
        """Should raise if no Groq key and no local whisper."""
        t = Transcriber(groq_api_key=None)
        with pytest.raises(RuntimeError, match="No STT backend"):
            with patch.dict("sys.modules", {"faster_whisper": None}):
                await t.transcribe("/tmp/test.ogg")


class TestTranscriberGroq:
    """Test Groq Whisper API integration."""

    @pytest.mark.asyncio
    async def test_groq_whisper_success(self):
        t = Transcriber(groq_api_key="test-key")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "text": "Рейс 4521, стою в пробке на МКАДе",
            "duration": 12.5,
        }

        with patch.object(t._client, "post", new_callable=AsyncMock, return_value=mock_response):
            # Create a temp file to simulate audio
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                f.write(b"fake audio data")
                temp_path = f.name

            try:
                result = await t.transcribe(temp_path)
                assert result["text"] == "Рейс 4521, стою в пробке на МКАДе"
                assert result["duration_sec"] == 12
                assert result["model"] == "groq-whisper-large-v3"
                assert result["duration_ms"] >= 0
            finally:
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_groq_whisper_empty_text(self):
        t = Transcriber(groq_api_key="test-key")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"text": "", "duration": 3.0}

        with patch.object(t._client, "post", new_callable=AsyncMock, return_value=mock_response):
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                f.write(b"fake")
                temp_path = f.name
            try:
                result = await t.transcribe(temp_path)
                assert result["text"] == ""
            finally:
                os.unlink(temp_path)


class TestVoiceHandler:
    """Test VoiceHandler (download + transcribe orchestration)."""

    def test_max_duration_constant(self):
        assert MAX_AUDIO_DURATION_SEC == 300  # 5 minutes

    @pytest.mark.asyncio
    async def test_bot_api_too_long_skipped(self):
        t = Transcriber(groq_api_key="test")
        vh = VoiceHandler(t)
        result = await vh.transcribe_voice_bot_api("/tmp/test.ogg", duration=600)
        assert result is None

    @pytest.mark.asyncio
    async def test_bot_api_success(self):
        mock_transcriber = AsyncMock()
        mock_transcriber.transcribe = AsyncMock(return_value={
            "text": "загрузка завершена, выезжаю",
            "duration_sec": 8,
            "model": "groq-whisper-large-v3",
            "duration_ms": 500,
        })

        vh = VoiceHandler(mock_transcriber)
        result = await vh.transcribe_voice_bot_api("/tmp/test.ogg", duration=8)
        assert result is not None
        assert result["text"] == "загрузка завершена, выезжаю"
        assert result["duration_sec"] == 8

    @pytest.mark.asyncio
    async def test_bot_api_empty_transcription(self):
        mock_transcriber = AsyncMock()
        mock_transcriber.transcribe = AsyncMock(return_value={
            "text": "",
            "duration_sec": 2,
            "model": "groq-whisper-large-v3",
            "duration_ms": 300,
        })

        vh = VoiceHandler(mock_transcriber)
        result = await vh.transcribe_voice_bot_api("/tmp/test.ogg", duration=2)
        assert result is None


class TestVoiceInPipeline:
    """Test that voice messages create correct IncomingMessage objects."""

    def test_voice_message_fields(self):
        msg = IncomingMessage(
            chat_id=12345,
            chat_name="DM:Диспетчер↔Водитель",
            sender_id=67890,
            sender_name="Водитель Сидоров",
            message_id=500,
            text="стою в пробке уже полчаса, опоздаю минут на 40",
            timestamp=1709800000.0,
            source_type="voice_transcription",
            is_voice=True,
            audio_duration_sec=15,
        )
        assert msg.is_voice is True
        assert msg.source_type == "voice_transcription"
        assert msg.audio_duration_sec == 15
        assert "пробке" in msg.text

    def test_text_message_not_voice(self):
        msg = IncomingMessage(
            chat_id=12345, chat_name="Chat", sender_id=1,
            sender_name="User", message_id=1, text="test", timestamp=1.0,
        )
        assert msg.is_voice is False
        assert msg.audio_duration_sec == 0
        assert msg.source_type == "group_chat"


class TestConfigParsing:
    """Test dispatcher session config parsing."""

    def test_parse_empty(self):
        from src.api.config import parse_dispatcher_sessions
        with patch.dict(os.environ, {"TG_DISPATCHER_SESSIONS": ""}):
            # Need to reimport since it reads env at import
            import importlib
            import src.api.config as cfg
            importlib.reload(cfg)
            result = cfg.parse_dispatcher_sessions()
            assert result == []

    def test_parse_valid_json(self):
        sessions = [
            {"session_string": "abc123", "dispatcher_name": "Диспетчер 1"},
            {"session_string": "def456", "dispatcher_name": "Диспетчер 2"},
        ]
        with patch.dict(os.environ, {"TG_DISPATCHER_SESSIONS": json.dumps(sessions)}):
            import importlib
            import src.api.config as cfg
            importlib.reload(cfg)
            result = cfg.parse_dispatcher_sessions()
            assert len(result) == 2
            assert result[0]["dispatcher_name"] == "Диспетчер 1"

    def test_parse_invalid_json(self):
        with patch.dict(os.environ, {"TG_DISPATCHER_SESSIONS": "not json"}):
            import importlib
            import src.api.config as cfg
            importlib.reload(cfg)
            result = cfg.parse_dispatcher_sessions()
            assert result == []
