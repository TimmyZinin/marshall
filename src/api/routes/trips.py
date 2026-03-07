from fastapi import APIRouter, Depends, Query
from typing import Optional
from src.db.connection import get_pool
from src.api.auth import get_current_user

router = APIRouter(prefix="/api/trips", tags=["trips"])


@router.get("")
async def list_trips(
    customer: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _user: dict = Depends(get_current_user),
):
    pool = await get_pool()
    conditions = []
    params = []
    idx = 1

    if customer:
        conditions.append(f"customer = ${idx}")
        params.append(customer)
        idx += 1
    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    offset = (page - 1) * limit

    total = await pool.fetchval(f"SELECT COUNT(*) FROM trips {where}", *params)
    rows = await pool.fetch(
        f"SELECT * FROM trips {where} ORDER BY updated_at DESC LIMIT ${idx} OFFSET ${idx+1}",
        *params, limit, offset,
    )
    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/{trip_id}")
async def get_trip(trip_id: str, _user: dict = Depends(get_current_user)):
    pool = await get_pool()
    trip = await pool.fetchrow("SELECT * FROM trips WHERE trip_id = $1", trip_id)
    if not trip:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Trip not found")

    alerts = await pool.fetch(
        "SELECT * FROM alerts WHERE trip_id = $1 ORDER BY created_at DESC", trip_id
    )
    messages = await pool.fetch(
        """SELECT pm.*, rm.text as raw_text, rm.sender_name, rm.timestamp as msg_time
           FROM parsed_messages pm
           JOIN raw_messages rm ON pm.raw_message_id = rm.id
           WHERE pm.trip_id = $1
           ORDER BY rm.timestamp DESC LIMIT 20""",
        trip_id,
    )
    return {
        "trip": dict(trip),
        "alerts": [dict(a) for a in alerts],
        "messages": [dict(m) for m in messages],
    }
