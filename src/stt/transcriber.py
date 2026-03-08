"""Speech-to-Text transcriber: Groq Whisper API (free) with local faster-whisper fallback."""
import logging
import os
import tempfile
import time

import httpx

logger = logging.getLogger("marshall.stt.transcriber")


class Transcriber:
    """Transcribes audio files to text using Groq Whisper API (primary)
    or local faster-whisper (fallback).

    Groq offers free Whisper large-v3 transcription — no GPU needed.
    """

    def __init__(self, groq_api_key: str | None = None):
        self._groq_key = groq_api_key
        self._client = httpx.AsyncClient(timeout=120.0)

    async def transcribe(self, audio_path: str, language: str = "ru") -> dict:
        """Transcribe audio file to text.

        Args:
            audio_path: Path to audio file (ogg, mp3, wav, m4a, etc.)
            language: Language hint (default: ru for Russian)

        Returns:
            dict with keys:
                - text: transcribed text
                - duration_sec: audio duration in seconds
                - model: which model was used
                - duration_ms: processing time in ms
        """
        if self._groq_key:
            try:
                return await self._transcribe_groq(audio_path, language)
            except Exception as e:
                logger.warning("Groq Whisper failed, trying local fallback: %s", e)

        # Fallback: local faster-whisper (if installed)
        try:
            return await self._transcribe_local(audio_path, language)
        except ImportError:
            logger.error("No STT backend available: Groq key missing and faster-whisper not installed")
            raise RuntimeError("No STT backend available")

    async def _transcribe_groq(self, audio_path: str, language: str) -> dict:
        """Transcribe via Groq Whisper API (free tier)."""
        start = time.monotonic()

        with open(audio_path, "rb") as f:
            files = {"file": (os.path.basename(audio_path), f, "audio/ogg")}
            data = {
                "model": "whisper-large-v3",
                "language": language,
                "response_format": "verbose_json",
            }
            resp = await self._client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self._groq_key}"},
                files=files,
                data=data,
            )
        resp.raise_for_status()
        result = resp.json()
        duration_ms = int((time.monotonic() - start) * 1000)

        text = result.get("text", "").strip()
        audio_duration = result.get("duration", 0)

        logger.info(
            "Groq Whisper transcribed %.1fs audio in %dms: %s",
            audio_duration, duration_ms, text[:80],
        )

        return {
            "text": text,
            "duration_sec": int(audio_duration),
            "model": "groq-whisper-large-v3",
            "duration_ms": duration_ms,
        }

    async def _transcribe_local(self, audio_path: str, language: str) -> dict:
        """Fallback: transcribe via local faster-whisper (CPU)."""
        import asyncio
        from functools import partial

        start = time.monotonic()

        def _run():
            from faster_whisper import WhisperModel
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, info = model.transcribe(audio_path, language=language)
            text = " ".join(s.text for s in segments).strip()
            return text, info.duration

        loop = asyncio.get_event_loop()
        text, audio_duration = await loop.run_in_executor(None, _run)
        duration_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "Local Whisper transcribed %.1fs audio in %dms: %s",
            audio_duration, duration_ms, text[:80],
        )

        return {
            "text": text,
            "duration_sec": int(audio_duration),
            "model": "faster-whisper-base-cpu",
            "duration_ms": duration_ms,
        }

    async def close(self):
        await self._client.aclose()
