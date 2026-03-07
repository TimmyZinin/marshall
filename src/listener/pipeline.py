"""Pipeline: Listener → Queue → Parser → DB."""
import asyncio
import logging

from src.listener.transport import IncomingMessage
from src.listener.storage import save_raw_message
from src.parser.core import MessageParser

logger = logging.getLogger("marshall.listener.pipeline")


class Pipeline:
    """Async pipeline: consumes messages from queue, saves to DB, parses via LLM."""

    def __init__(self, queue: asyncio.Queue, parser: MessageParser, workers: int = 2):
        self._queue = queue
        self._parser = parser
        self._workers = workers
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        for i in range(self._workers):
            task = asyncio.create_task(self._worker(i))
            self._tasks.append(task)
        logger.info("Pipeline started with %d workers", self._workers)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Pipeline stopped")

    async def _worker(self, worker_id: int) -> None:
        while True:
            try:
                msg: IncomingMessage = await self._queue.get()
                logger.debug("Worker %d processing message %d", worker_id, msg.message_id)

                # Save raw message
                raw_id = await save_raw_message(msg)
                if not raw_id:
                    self._queue.task_done()
                    continue

                # Parse via LLM
                await self._parser.parse_message(
                    raw_message_id=raw_id,
                    text=msg.text,
                    sender_name=msg.sender_name,
                    chat_name=msg.chat_name,
                )
                self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Worker %d error: %s", worker_id, e)
                await asyncio.sleep(1)
