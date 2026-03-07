from fastapi import APIRouter, Depends
from src.db.connection import get_pool
from src.api.auth import get_current_user

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/summary")
async def get_summary(_user: dict = Depends(get_current_user)):
    pool = await get_pool()
    trips_active = await pool.fetchval(
        "SELECT COUNT(*) FROM trips WHERE status NOT IN ('completed', 'cancelled')"
    )
    trips_total = await pool.fetchval("SELECT COUNT(*) FROM trips")
    alerts_new = await pool.fetchval("SELECT COUNT(*) FROM alerts WHERE status = 'new'")
    alerts_high = await pool.fetchval(
        "SELECT COUNT(*) FROM alerts WHERE severity = 'high' AND status != 'resolved'"
    )
    alerts_total = await pool.fetchval("SELECT COUNT(*) FROM alerts")
    alerts_resolved = await pool.fetchval("SELECT COUNT(*) FROM alerts WHERE status = 'resolved'")
    messages_total = await pool.fetchval("SELECT COUNT(*) FROM raw_messages")

    return {
        "trips_active": trips_active,
        "trips_total": trips_total,
        "alerts_new": alerts_new,
        "alerts_high": alerts_high,
        "alerts_total": alerts_total,
        "alerts_resolved": alerts_resolved,
        "resolve_rate": round(alerts_resolved / alerts_total * 100, 1) if alerts_total > 0 else 0,
        "messages_total": messages_total,
    }


@router.get("/timeline")
async def get_timeline(_user: dict = Depends(get_current_user)):
    pool = await get_pool()
    rows = await pool.fetch(
        """SELECT date_trunc('day', created_at)::date AS day,
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE severity = 'high') AS high,
                  COUNT(*) FILTER (WHERE severity = 'medium') AS medium,
                  COUNT(*) FILTER (WHERE severity = 'low') AS low
           FROM alerts
           WHERE created_at >= NOW() - INTERVAL '14 days'
           GROUP BY day ORDER BY day"""
    )
    return {"items": [dict(r) for r in rows]}


@router.get("/by-customer")
async def get_by_customer(_user: dict = Depends(get_current_user)):
    pool = await get_pool()
    rows = await pool.fetch(
        """SELECT customer, COUNT(*) AS alert_count,
                  COUNT(*) FILTER (WHERE severity = 'high') AS high_count
           FROM alerts WHERE customer IS NOT NULL
           GROUP BY customer ORDER BY alert_count DESC"""
    )
    return {"items": [dict(r) for r in rows]}
