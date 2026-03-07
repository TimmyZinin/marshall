"""Alert Engine — generates alerts from parsed messages based on customer rules."""
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.db.connection import get_pool

logger = logging.getLogger("marshall.alerts.engine")

ALERT_TYPES = {"delay", "equipment_failure", "downtime", "safety_violation", "docs_missing"}

# Issue keywords that map to alert types
ISSUE_KEYWORDS = {
    "delay": ["опоздание", "опаздыва", "задержка", "задержи", "пробка", "пробк", "не успе"],
    "equipment_failure": ["реф", "компрессор", "температур", "поломка", "сломал", "не работа", "отказ"],
    "downtime": ["простой", "простаива", "жду", "ожидани", "очередь", "очеред"],
    "safety_violation": ["каска", "жилет", "без каски", "без жилета", "охрана труда"],
    "docs_missing": ["термограмм", "накладн", "ТТН", "документ", "забыл", "нет документ"],
}


class AlertEngine:
    """Evaluates parsed messages and creates alerts based on YAML rules."""

    def __init__(self, rules_path: str | None = None):
        if rules_path is None:
            rules_path = str(Path(__file__).parent.parent.parent / "config" / "alert_rules.yaml")
        with open(rules_path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f)
        self._defaults = self._config.get("defaults", {})
        self._customers = self._config.get("customers", {})
        logger.info("Alert engine loaded: %d customer rules", len(self._customers))

    async def evaluate(self, parsed_message_id: int) -> list[int]:
        """Evaluate a parsed message and create alerts. Returns list of alert IDs."""
        pool = await get_pool()
        pm = await pool.fetchrow(
            """SELECT id, trip_id, route_from, route_to, status, customer,
                      urgency, issue, confidence
               FROM parsed_messages WHERE id = $1""",
            parsed_message_id,
        )
        if not pm:
            return []

        # Skip low-confidence parses
        min_confidence = self._defaults.get("confidence_threshold", 0.6)
        if pm["confidence"] < min_confidence:
            logger.debug("Skipping low-confidence parse %d (%.2f)", parsed_message_id, pm["confidence"])
            return []

        # Detect alert types from issue text and status
        detected_types = self._detect_alert_types(pm)
        if not detected_types:
            return []

        customer = pm["customer"] or "unknown"
        customer_rules = self._customers.get(customer, {})

        alert_ids = []
        for alert_type in detected_types:
            rule = customer_rules.get(alert_type, {})
            severity = rule.get("severity", self._severity_from_urgency(pm["urgency"]))
            message = self._build_alert_message(alert_type, pm, rule)

            alert_id = await self._create_alert(
                pool=pool,
                trip_id=pm["trip_id"],
                parsed_message_id=parsed_message_id,
                alert_type=alert_type,
                severity=severity,
                message=message,
                customer=customer,
            )
            if alert_id:
                alert_ids.append(alert_id)

        return alert_ids

    def _detect_alert_types(self, pm) -> set[str]:
        """Detect which alert types apply based on issue text, status, and urgency."""
        types = set()
        issue = (pm["issue"] or "").lower()
        status = pm["status"]
        urgency = pm["urgency"]

        # Check issue keywords
        for alert_type, keywords in ISSUE_KEYWORDS.items():
            if any(kw in issue for kw in keywords):
                types.add(alert_type)

        # Status-based detection
        if status == "problem" and urgency in ("high", "medium") and not types:
            types.add("delay")  # default problem type if no specific issue

        return types

    def _severity_from_urgency(self, urgency: str) -> str:
        return {"high": "high", "medium": "medium", "low": "low"}.get(urgency, "medium")

    def _build_alert_message(self, alert_type: str, pm, rule: dict) -> str:
        trip_id = pm["trip_id"] or "N/A"
        customer = pm["customer"] or ""
        issue = pm["issue"] or ""

        if alert_type == "delay":
            fine_text = rule.get("fine_text", "")
            base = f"Рейс {trip_id}: задержка/опоздание."
            if fine_text:
                base += f" {fine_text}"
            if issue:
                base += f" Причина: {issue}"
            return base

        if alert_type == "equipment_failure":
            return f"Рейс {trip_id}: неисправность оборудования. {issue}"

        if alert_type == "downtime":
            return f"Рейс {trip_id}: простой на территории {customer}. {issue}"

        if alert_type == "safety_violation":
            return f"Рейс {trip_id}: нарушение ТБ на территории {customer}. {issue}"

        if alert_type == "docs_missing":
            required = rule.get("required", [])
            docs = ", ".join(required) if required else "документы"
            return f"Рейс {trip_id}: отсутствуют {docs}. {issue}"

        return f"Рейс {trip_id}: {alert_type}. {issue}"

    async def _create_alert(self, pool, trip_id, parsed_message_id, alert_type, severity, message, customer) -> int | None:
        try:
            alert_id = await pool.fetchval(
                """INSERT INTO alerts (trip_id, parsed_message_id, type, severity, message, customer, status, created_at)
                   VALUES ($1, $2, $3, $4, $5, $6, 'new', $7) RETURNING id""",
                trip_id, parsed_message_id, alert_type, severity, message, customer,
                datetime.now(timezone.utc),
            )
            if trip_id:
                await pool.execute(
                    "UPDATE trips SET alert_count = alert_count + 1, updated_at = NOW() WHERE trip_id = $1",
                    trip_id,
                )
            logger.info("Alert created: [%s/%s] trip=%s — %s", alert_type, severity, trip_id, message[:80])
            return alert_id
        except Exception as e:
            logger.error("Failed to create alert: %s", e)
            return None
