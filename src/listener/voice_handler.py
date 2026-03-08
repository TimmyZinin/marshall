"""Voice message handler — downloads audio and transcribes to text."""
import logging
import os
import tempfile
from pathlib import Path

from src.stt.transcriber import Transcriber

logger = logging.getLogger("marshall.listener.voice_handler")

# Max audio duration to process (5 minutes)
MAX_AUDIO_DURATION_SEC = 300
# Temp directory for downloaded audio files
AUDIO_TEMP_DIR = Path(tempfile.gettempdir()) / "marshall_audio"


class VoiceHandler:
    """Downloads voice/audio messages and transcribes them."""

    def __init__(self, transcriber: Transcriber):
        self._transcriber = transcriber
        AUDIO_TEMP_DIR.mkdir(parents=True, exist_ok=True)

    async def transcribe_voice_telethon(self, message, dispatcher_name: str = "") -> dict | None:
        """Download and transcribe a Telethon voice/audio message.

        Args:
            message: Telethon Message object with voice/audio.
            dispatcher_name: For logging.

        Returns:
            dict with 'text', 'duration_sec', 'model', 'duration_ms' or None if failed.
        """
        try:
            # Check if it's voice or audio
            media = message.media
            if not media:
                return None

            # Get duration from media attributes
            duration = 0
            if hasattr(message, "voice") and message.voice:
                duration = message.voice.duration or 0
            elif hasattr(message, "audio") and message.audio:
                duration = message.audio.duration or 0
            elif hasattr(message, "video_note") and message.video_note:
                duration = message.video_note.duration or 0

            if duration > MAX_AUDIO_DURATION_SEC:
                logger.warning(
                    "[%s] Skipping audio msg %d: too long (%ds > %ds)",
                    dispatcher_name, message.id, duration, MAX_AUDIO_DURATION_SEC,
                )
                return None

            # Download to temp file
            audio_path = AUDIO_TEMP_DIR / f"voice_{message.id}_{message.chat_id}.ogg"
            await message.download_media(file=str(audio_path))

            if not audio_path.exists() or audio_path.stat().st_size == 0:
                logger.error("[%s] Downloaded audio is empty: msg %d", dispatcher_name, message.id)
                return None

            logger.info(
                "[%s] Downloaded voice msg %d (%.1f KB, %ds)",
                dispatcher_name, message.id, audio_path.stat().st_size / 1024, duration,
            )

            # Transcribe
            result = await self._transcriber.transcribe(str(audio_path))

            # Cleanup temp file
            try:
                audio_path.unlink()
            except OSError:
                pass

            if not result.get("text"):
                logger.info("[%s] Empty transcription for msg %d", dispatcher_name, message.id)
                return None

            result["duration_sec"] = duration or result.get("duration_sec", 0)
            return result

        except Exception as e:
            logger.error("[%s] Voice transcription failed for msg %d: %s", dispatcher_name, message.id, e)
            return None

    async def transcribe_voice_bot_api(self, file_path: str, duration: int = 0) -> dict | None:
        """Transcribe a voice file already downloaded via Bot API.

        Args:
            file_path: Path to the downloaded audio file.
            duration: Audio duration in seconds.

        Returns:
            dict with 'text', 'duration_sec', 'model', 'duration_ms' or None.
        """
        try:
            if duration > MAX_AUDIO_DURATION_SEC:
                logger.warning("Skipping audio: too long (%ds)", duration)
                return None

            result = await self._transcriber.transcribe(file_path)

            if not result.get("text"):
                return None

            result["duration_sec"] = duration or result.get("duration_sec", 0)
            return result

        except Exception as e:
            logger.error("Bot API voice transcription failed: %s", e)
            return None
