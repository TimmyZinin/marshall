"""MTProto transport — reads DM messages from dispatcher's Telegram account via Telethon."""
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession

from src.listener.transport import ListenerTransport, IncomingMessage
from src.listener.voice_handler import VoiceHandler

logger = logging.getLogger("marshall.listener.mtproto")


class MTProtoTransport(ListenerTransport):
    """Telethon-based listener for reading DM messages from dispatcher accounts.

    Supports multiple dispatcher sessions simultaneously.
    Each session connects to one dispatcher's Telegram account
    and listens for incoming private (DM) messages.
    """

    def __init__(
        self,
        queue: asyncio.Queue,
        api_id: int,
        api_hash: str,
        sessions: list[dict] | None = None,
        listen_groups: bool = False,
        voice_handler: VoiceHandler | None = None,
    ):
        """
        Args:
            queue: Pipeline message queue.
            api_id: Telegram API ID.
            api_hash: Telegram API hash.
            sessions: List of dicts with keys:
                - session_string: Telethon StringSession
                - dispatcher_name: Human-readable name
                - dispatcher_id: (optional) Telegram user ID
            listen_groups: Also listen to group messages (default: DM only).
            voice_handler: VoiceHandler for transcribing voice/audio messages.
        """
        super().__init__(queue)
        self._api_id = api_id
        self._api_hash = api_hash
        self._sessions = sessions or []
        self._listen_groups = listen_groups
        self._voice_handler = voice_handler
        self._clients: list[TelegramClient] = []

    async def start(self) -> None:
        if not self._sessions:
            logger.warning("No dispatcher sessions configured — MTProto transport idle")
            return

        for sess_info in self._sessions:
            session_str = sess_info.get("session_string", "")
            dispatcher_name = sess_info.get("dispatcher_name", "unknown")
            if not session_str:
                logger.warning("Empty session string for dispatcher %s, skipping", dispatcher_name)
                continue

            try:
                client = TelegramClient(
                    StringSession(session_str),
                    self._api_id,
                    self._api_hash,
                )
                await client.connect()

                if not await client.is_user_authorized():
                    logger.error("Session for dispatcher %s is not authorized", dispatcher_name)
                    await client.disconnect()
                    continue

                me = await client.get_me()
                logger.info(
                    "MTProto connected: dispatcher=%s (id=%d, phone=%s)",
                    dispatcher_name, me.id, me.phone or "N/A",
                )

                # Register event handler for new messages
                @client.on(events.NewMessage(incoming=True))
                async def handler(event, _name=dispatcher_name, _client=client):
                    await self._on_message(event, _name)

                self._clients.append(client)
                logger.info("MTProto listener started for dispatcher: %s", dispatcher_name)

            except Exception as e:
                logger.error("Failed to start MTProto for dispatcher %s: %s", dispatcher_name, e)

        if self._clients:
            logger.info("MTProto transport started with %d dispatcher sessions", len(self._clients))
        else:
            logger.warning("MTProto transport: no sessions connected")

    async def stop(self) -> None:
        for client in self._clients:
            try:
                await client.disconnect()
            except Exception as e:
                logger.warning("Error disconnecting MTProto client: %s", e)
        self._clients.clear()
        logger.info("MTProto transport stopped")

    async def _on_message(self, event, dispatcher_name: str) -> None:
        """Handle incoming message from Telethon (text + voice)."""
        msg = event.message
        if not msg:
            return

        # Determine if DM or group
        is_private = event.is_private
        is_group = event.is_group or event.is_channel

        if is_private:
            source_type = "dm"
        elif is_group and self._listen_groups:
            source_type = "group_chat"
        else:
            return

        # Check if voice/audio message
        is_voice = bool(msg.voice or msg.audio or msg.video_note)
        has_text = bool(msg.text)

        if not has_text and not is_voice:
            return  # Skip media without text and non-voice

        # Get sender info
        sender = await event.get_sender()
        sender_name = ""
        sender_id = 0
        if sender:
            sender_id = sender.id
            if hasattr(sender, "first_name"):
                parts = [sender.first_name or "", sender.last_name or ""]
                sender_name = " ".join(p for p in parts if p).strip()
            if not sender_name and hasattr(sender, "username"):
                sender_name = sender.username or str(sender.id)

        # Get chat info
        chat = await event.get_chat()
        chat_name = ""
        chat_id = event.chat_id or 0
        if hasattr(chat, "title") and chat.title:
            chat_name = chat.title
        elif is_private:
            chat_name = f"DM:{dispatcher_name}↔{sender_name}"
        else:
            chat_name = str(chat_id)

        # Handle voice: transcribe first
        text = msg.text or ""
        audio_duration = 0
        actual_source = source_type

        if is_voice and self._voice_handler:
            result = await self._voice_handler.transcribe_voice_telethon(msg, dispatcher_name)
            if result and result.get("text"):
                text = result["text"]
                audio_duration = result.get("duration_sec", 0)
                actual_source = "voice_transcription"
                logger.info(
                    "[%s] Voice transcribed (%ds): %s",
                    dispatcher_name, audio_duration, text[:80],
                )
            elif not has_text:
                return  # Voice failed to transcribe and no text — skip
        elif is_voice and not self._voice_handler:
            if not has_text:
                logger.debug("[%s] Skipping voice msg %d: no STT configured", dispatcher_name, msg.id)
                return

        if not text:
            return

        incoming = IncomingMessage(
            chat_id=chat_id,
            chat_name=chat_name,
            sender_id=sender_id,
            sender_name=sender_name,
            message_id=msg.id,
            text=text,
            timestamp=msg.date.timestamp(),
            source_type=actual_source,
            is_voice=is_voice,
            audio_duration_sec=audio_duration,
        )
        await self._emit(incoming)
        logger.debug(
            "[%s] %s message from %s: %s",
            dispatcher_name, actual_source, sender_name, text[:80],
        )
