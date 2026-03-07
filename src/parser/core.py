"""Core parser: raw message → LLM → structured data → DB."""
import logging
from datetime import datetime, timezone

from src.db.connection import get_pool
from src.parser.llm import LLMClient
from src.parser.prompt import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

logger = logging.getLogger("marshall.parser.core")

VALID_STATUSES = {"assigned", "in_transit", "loading", "unloading", "completed", "problem", "cancelled"}
VALID_URGENCIES = {"low", "medium", "high"}


class MessageParser:
    """Parses raw messages using LLM and saves to parsed_messages + updates trips."""

    def __init__(self, llm: LLMClient):
        self._llm = llm

    async def parse_message(self, raw_message_id: int, text: str, sender_name: str, chat_name: str) -> int | None:
        """Parse a raw message and save result. Returns parsed_message id or None."""
        user_prompt = USER_PROMPT_TEMPLATE.format(
            sender_name=sender_name,
            chat_name=chat_name,
            text=text,
        )

        try:
            result, model, tokens, duration_ms = await self._llm.parse(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            logger.error("LLM parse failed for raw_message %d: %s", raw_message_id, e)
            return None

        if result.get("skip"):
            logger.debug("Skipped non-logistics message %d", raw_message_id)
            return None

        # Validate and normalize
        status = result.get("status")
        if status not in VALID_STATUSES:
            status = None
        urgency = result.get("urgency", "low")
        if urgency not in VALID_URGENCIES:
            urgency = "low"
        confidence = result.get("confidence", 0.5)
        confidence = max(0.0, min(1.0, float(confidence)))

        pool = await get_pool()
        try:
            pm_id = await pool.fetchval(
                """INSERT INTO parsed_messages
                   (raw_message_id, trip_id, route_from, route_to, status, customer,
                    urgency, issue, confidence, llm_model, llm_tokens_used, parse_duration_ms, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                   RETURNING id""",
                raw_message_id,
                result.get("trip_id"),
                result.get("route_from"),
                result.get("route_to"),
                status,
                result.get("customer"),
                urgency,
                result.get("issue"),
                confidence,
                model,
                tokens,
                duration_ms,
                datetime.now(timezone.utc),
            )
            logger.info(
                "Parsed message %d → trip=%s status=%s urgency=%s (model=%s, %dms)",
                raw_message_id, result.get("trip_id"), status, urgency, model, duration_ms,
            )

            # Update trip aggregation if trip_id exists
            trip_id = result.get("trip_id")
            if trip_id and status:
                await _upsert_trip(pool, trip_id, result, status)

            return pm_id
        except Exception as e:
            logger.error("Failed to save parsed message for raw %d: %s", raw_message_id, e)
            return None


async def _upsert_trip(pool, trip_id: str, parsed: dict, status: str) -> None:
    """Create or update trip from parsed message data."""
    now = datetime.now(timezone.utc)
    existing = await pool.fetchrow("SELECT id FROM trips WHERE trip_id = $1", trip_id)
    if existing:
        await pool.execute(
            """UPDATE trips SET
               status = COALESCE($2, status),
               route_from = COALESCE($3, route_from),
               route_to = COALESCE($4, route_to),
               customer = COALESCE($5, customer),
               updated_at = $6, last_update = $6
               WHERE trip_id = $1""",
            trip_id, status, parsed.get("route_from"), parsed.get("route_to"),
            parsed.get("customer"), now,
        )
    else:
        await pool.execute(
            """INSERT INTO trips (trip_id, route_from, route_to, customer, status,
               created_at, updated_at, last_update)
               VALUES ($1,$2,$3,$4,$5,$6,$6,$6)
               ON CONFLICT (trip_id) DO NOTHING""",
            trip_id, parsed.get("route_from"), parsed.get("route_to"),
            parsed.get("customer"), status, now,
        )
