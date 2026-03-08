"""Save incoming messages to raw_messages table."""
import logging
from datetime import datetime, timezone

from src.db.connection import get_pool
from src.listener.transport import IncomingMessage

logger = logging.getLogger("marshall.listener.storage")


async def save_raw_message(msg: IncomingMessage) -> int | None:
    """Save raw message to DB, return id. Returns None if duplicate."""
    pool = await get_pool()
    try:
        row_id = await pool.fetchval(
            """INSERT INTO raw_messages (chat_id, chat_name, sender_id, sender_name,
               message_id, text, timestamp, source_type, is_voice, audio_duration_sec)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
               ON CONFLICT (chat_id, message_id) DO NOTHING
               RETURNING id""",
            msg.chat_id,
            msg.chat_name,
            msg.sender_id,
            msg.sender_name,
            msg.message_id,
            msg.text,
            datetime.fromtimestamp(msg.timestamp, tz=timezone.utc),
            msg.source_type,
            msg.is_voice,
            msg.audio_duration_sec,
        )
        if row_id:
            logger.info(
                "Saved raw message %d from %s [%s%s]",
                msg.message_id, msg.chat_name, msg.source_type,
                " voice" if msg.is_voice else "",
            )
        return row_id
    except Exception as e:
        logger.error("Failed to save message %d: %s", msg.message_id, e)
        return None
