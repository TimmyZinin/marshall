import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path

from src.api.config import (
    CORS_ORIGINS, DEMO_MODE, TG_BOT_TOKEN, TG_ALLOWED_CHATS,
    MINIMAX_API_KEY, GROQ_API_KEY,
    TG_API_ID, TG_API_HASH, MTPROTO_LISTEN_GROUPS,
    STT_ENABLED, parse_dispatcher_sessions,
)
from src.db.connection import get_pool, close_pool
from src.api.routes import auth, trips, alerts, stats, config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("marshall")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Marshall AI Listener API (demo_mode=%s)", DEMO_MODE)
    pool = await get_pool()

    # Run migrations
    migrations_dir = Path(__file__).parent.parent / "db" / "migrations"
    for mig in sorted(migrations_dir.glob("*.sql")):
        await pool.execute(mig.read_text())
    logger.info("Migrations applied")

    # Seed demo data if tables empty
    if DEMO_MODE:
        count = await pool.fetchval("SELECT COUNT(*) FROM trips")
        if count == 0:
            logger.info("Demo mode: seeding data...")
            await _seed_demo_data(pool)
            logger.info("Demo data seeded")

    # Start demo simulator or live listener(s)
    sim_task = None
    transports = []
    pipeline = None
    llm_client = None
    transcriber = None

    if DEMO_MODE:
        sim_task = asyncio.create_task(_demo_simulator())
        logger.info("Demo simulator started")
    else:
        llm_client, transports, pipeline, transcriber = await _start_live_listeners()
        if transports:
            logger.info("Live listeners started: %d transports", len(transports))
        else:
            logger.warning("No transports configured — nothing to listen to")

    yield

    if sim_task:
        sim_task.cancel()
    if pipeline:
        await pipeline.stop()
    for t in transports:
        await t.stop()
    if llm_client:
        await llm_client.close()
    if transcriber:
        await transcriber.close()
    await close_pool()
    logger.info("Marshall API shut down")


app = FastAPI(title="Marshall AI Listener", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(trips.router)
app.include_router(alerts.router)
app.include_router(stats.router)
app.include_router(config.router)

# Serve frontend
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/api/health")
async def health():
    pool = await get_pool()
    await pool.fetchval("SELECT 1")
    return {"status": "ok", "demo_mode": DEMO_MODE}


@app.get("/")
async def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/{path:path}")
async def serve_static(path: str):
    file_path = FRONTEND_DIR / path
    if file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(FRONTEND_DIR / "index.html")


async def _start_live_listeners():
    """Initialize and start all configured live listener transports."""
    from src.listener.bot_api import BotApiTransport
    from src.listener.pipeline import Pipeline
    from src.parser.llm import LLMClient
    from src.parser.core import MessageParser
    from src.alerts.engine import AlertEngine

    queue = asyncio.Queue(maxsize=100)
    llm_client = LLMClient(
        minimax_api_key=MINIMAX_API_KEY or None,
        groq_api_key=GROQ_API_KEY or None,
    )
    parser = MessageParser(llm_client)
    alert_engine = AlertEngine()
    pipeline = Pipeline(queue, parser, alert_engine=alert_engine, workers=2)

    transports = []
    transcriber = None

    # Initialize STT if enabled
    if STT_ENABLED and GROQ_API_KEY:
        from src.stt.transcriber import Transcriber
        transcriber = Transcriber(groq_api_key=GROQ_API_KEY)
        logger.info("STT enabled (Groq Whisper)")

    # Initialize voice handler
    voice_handler = None
    if transcriber:
        from src.listener.voice_handler import VoiceHandler
        voice_handler = VoiceHandler(transcriber)

    # Transport 1: Bot API (group chats)
    if TG_BOT_TOKEN:
        bot_transport = BotApiTransport(TG_BOT_TOKEN, queue, TG_ALLOWED_CHATS or None)
        await bot_transport.start()
        transports.append(bot_transport)
        logger.info("Bot API transport started")

    # Transport 2: MTProto (DM + optionally groups)
    dispatcher_sessions = parse_dispatcher_sessions()
    if TG_API_ID and TG_API_HASH and dispatcher_sessions:
        from src.listener.mtproto import MTProtoTransport
        mtproto_transport = MTProtoTransport(
            queue=queue,
            api_id=TG_API_ID,
            api_hash=TG_API_HASH,
            sessions=dispatcher_sessions,
            listen_groups=MTPROTO_LISTEN_GROUPS,
            voice_handler=voice_handler,
        )
        await mtproto_transport.start()
        transports.append(mtproto_transport)
        logger.info("MTProto transport started (%d sessions)", len(dispatcher_sessions))

    await pipeline.start()
    return llm_client, transports, pipeline, transcriber


async def _seed_demo_data(pool):
    from src.db.seed import seed_demo
    await seed_demo(pool)


async def _demo_simulator():
    """Background task: periodically update trip statuses and add new alerts."""
    import random
    from datetime import datetime, timezone

    TRANSITIONS = {
        "assigned": ["in_transit"],
        "in_transit": ["loading", "problem"],
        "loading": ["in_transit"],
        "unloading": ["completed"],
    }

    ALERT_MSGS = [
        ("delay", "high", "Рейс {trip}: задержка {mins} мин. Водитель в пробке."),
        ("equipment_failure", "high", "Рейс {trip}: реф не выходит на температуру +{temp}C."),
        ("downtime", "medium", "Рейс {trip}: простой на территории клиента > {hrs} ч."),
        ("docs_missing", "medium", "Рейс {trip}: отсутствует термограмма."),
        ("safety_violation", "low", "Рейс {trip}: водитель без жилета на территории клиента."),
    ]

    while True:
        try:
            await asyncio.sleep(random.randint(30, 90))
            pool = await get_pool()

            # 50% chance: update a random active trip status
            if random.random() > 0.5:
                trip = await pool.fetchrow(
                    "SELECT trip_id, status FROM trips WHERE status NOT IN ('completed', 'cancelled') ORDER BY RANDOM() LIMIT 1"
                )
                if trip and trip["status"] in TRANSITIONS:
                    new_status = random.choice(TRANSITIONS[trip["status"]])
                    await pool.execute(
                        "UPDATE trips SET status = $1, updated_at = NOW(), last_update = NOW() WHERE trip_id = $2",
                        new_status, trip["trip_id"],
                    )
                    logger.debug("Demo sim: trip %s → %s", trip["trip_id"], new_status)

            # 30% chance: add a new alert to an active trip
            if random.random() > 0.7:
                pm = await pool.fetchrow(
                    """SELECT pm.id, pm.trip_id, t.customer FROM parsed_messages pm
                       JOIN trips t ON pm.trip_id = t.trip_id
                       WHERE t.status NOT IN ('completed', 'cancelled')
                       ORDER BY RANDOM() LIMIT 1"""
                )
                if pm:
                    atype, sev, tmpl = random.choice(ALERT_MSGS)
                    msg = tmpl.format(
                        trip=pm["trip_id"],
                        mins=random.randint(20, 120),
                        temp=random.randint(5, 12),
                        hrs=random.randint(2, 6),
                    )
                    await pool.execute(
                        """INSERT INTO alerts (trip_id, parsed_message_id, type, severity, message, customer, status, created_at)
                           VALUES ($1, $2, $3, $4, $5, $6, 'new', NOW())""",
                        pm["trip_id"], pm["id"], atype, sev, msg, pm["customer"],
                    )
                    await pool.execute(
                        "UPDATE trips SET alert_count = alert_count + 1, updated_at = NOW() WHERE trip_id = $1",
                        pm["trip_id"],
                    )
                    logger.debug("Demo sim: new %s alert for trip %s", atype, pm["trip_id"])

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("Demo simulator error: %s", e)
            await asyncio.sleep(10)
