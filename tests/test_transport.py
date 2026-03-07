"""Tests for listener transport abstraction."""
import asyncio
import pytest
from src.listener.transport import IncomingMessage, ListenerTransport


class DummyTransport(ListenerTransport):
    async def start(self):
        pass

    async def stop(self):
        pass


@pytest.mark.asyncio
async def test_incoming_message_creation():
    msg = IncomingMessage(
        chat_id=-1001234567890,
        chat_name="Test Chat",
        sender_id=12345,
        sender_name="Test User",
        message_id=100,
        text="Рейс 4521, выехал из Москвы",
        timestamp=1709800000.0,
    )
    assert msg.chat_id == -1001234567890
    assert msg.text == "Рейс 4521, выехал из Москвы"


@pytest.mark.asyncio
async def test_transport_emit():
    queue = asyncio.Queue()
    transport = DummyTransport(queue)

    msg = IncomingMessage(
        chat_id=-100, chat_name="Chat", sender_id=1, sender_name="User",
        message_id=1, text="test", timestamp=1.0,
    )
    await transport._emit(msg)

    result = await queue.get()
    assert result.message_id == 1
    assert result.text == "test"
