"""Pipeline: Listener → Queue → Parser → Alert Engine → DB."""
import asyncio
import logging

from src.listener.transport import IncomingMessage
from src.listener.storage import save_raw_message
from src.parser.core import MessageParser
from src.alerts.engine import AlertEngine

logger = logging.getLogger("marshall.listener.pipeline")


class Pipeline:
    """Async pipeline: consumes messages from queue, saves to DB, parses via LLM, evaluates alerts."""

    def __init__(self, queue: asyncio.Queue, parser: MessageParser,
                 alert_engine: AlertEngine | None = None, workers: int = 2):
        self._queue = queue
        self._parser = parser
        self._alert_engine = alert_engine
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

                # 1. Save raw message
                raw_id = await save_raw_message(msg)
                if not raw_id:
                    self._queue.task_done()
                    continue

                # 2. Parse via LLM
                pm_id = await self._parser.parse_message(
                    raw_message_id=raw_id,
                    text=msg.text,
                    sender_name=msg.sender_name,
                    chat_name=msg.chat_name,
                )

                # 3. Evaluate alerts
                if pm_id and self._alert_engine:
                    alert_ids = await self._alert_engine.evaluate(pm_id)
                    if alert_ids:
                        logger.info("Created %d alerts for parsed message %d", len(alert_ids), pm_id)

                self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Worker %d error: %s", worker_id, e)
                await asyncio.sleep(1)
