"""Pluggable transport abstraction for Telegram message listeners."""
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class IncomingMessage:
    """Normalized message from any transport (Bot API, MTProto, etc.)."""
    chat_id: int
    chat_name: str
    sender_id: int
    sender_name: str
    message_id: int
    text: str
    timestamp: float  # unix timestamp


class ListenerTransport(ABC):
    """Abstract transport — swap Bot API for MTProto/Max without changing pipeline."""

    def __init__(self, queue: asyncio.Queue):
        self._queue = queue

    @abstractmethod
    async def start(self) -> None:
        """Start listening for messages."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop listening."""

    async def _emit(self, msg: IncomingMessage) -> None:
        await self._queue.put(msg)
