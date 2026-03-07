"""Bot API transport — listens to group messages via Telegram Bot API polling."""
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

from src.listener.transport import ListenerTransport, IncomingMessage

logger = logging.getLogger("marshall.listener.bot_api")


class BotApiTransport(ListenerTransport):
    """Telegram Bot API listener using python-telegram-bot."""

    def __init__(self, token: str, queue: asyncio.Queue, allowed_chats: list[int] | None = None):
        super().__init__(queue)
        self._token = token
        self._allowed_chats = set(allowed_chats) if allowed_chats else None
        self._app: Application | None = None

    async def start(self) -> None:
        self._app = Application.builder().token(self._token).build()
        self._app.add_handler(
            MessageHandler(filters.TEXT & filters.ChatType.GROUPS, self._on_message)
        )
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot API listener started (polling)")

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Bot API listener stopped")

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if not msg or not msg.text:
            return

        chat = update.effective_chat
        if self._allowed_chats and chat.id not in self._allowed_chats:
            return

        user = update.effective_user
        sender_name = ""
        if user:
            sender_name = user.full_name or user.username or str(user.id)

        incoming = IncomingMessage(
            chat_id=chat.id,
            chat_name=chat.title or str(chat.id),
            sender_id=user.id if user else 0,
            sender_name=sender_name,
            message_id=msg.message_id,
            text=msg.text,
            timestamp=msg.date.timestamp(),
        )
        await self._emit(incoming)
        logger.debug("Message from chat %s (%s): %s", chat.id, chat.title, msg.text[:80])
