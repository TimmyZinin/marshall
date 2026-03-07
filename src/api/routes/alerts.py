from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from src.db.connection import get_pool
from src.api.auth import get_current_user, require_role

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class AlertPatch(BaseModel):
    status: str


@router.get("")
async def list_alerts(
    severity: Optional[str] = None,
    status: Optional[str] = None,
    customer: Optional[str] = None,
    alert_type: Optional[str] = Query(None, alias="type"),
    trip_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _user: dict = Depends(get_current_user),
):
    pool = await get_pool()
    conditions = []
    params = []
    idx = 1

    for field, val in [("severity", severity), ("status", status),
                       ("customer", customer), ("type", alert_type), ("trip_id", trip_id)]:
        if val:
            conditions.append(f"{field} = ${idx}")
            params.append(val)
            idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    offset = (page - 1) * limit

    total = await pool.fetchval(f"SELECT COUNT(*) FROM alerts {where}", *params)
    rows = await pool.fetch(
        f"""SELECT * FROM alerts {where}
            ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                     created_at DESC
            LIMIT ${idx} OFFSET ${idx+1}""",
        *params, limit, offset,
    )
    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.patch("/{alert_id}")
async def update_alert(
    alert_id: int,
    body: AlertPatch,
    user: dict = Depends(require_role("admin", "manager")),
):
    if body.status not in ("reviewed", "resolved"):
        raise HTTPException(status_code=400, detail="Status must be 'reviewed' or 'resolved'")

    pool = await get_pool()
    row = await pool.fetchrow("SELECT id, status FROM alerts WHERE id = $1", alert_id)
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")

    await pool.execute(
        "UPDATE alerts SET status = $1, reviewed_by = $2, reviewed_at = NOW() WHERE id = $3",
        body.status, user["sub"], alert_id,
    )
    return {"id": alert_id, "status": body.status, "reviewed_by": user["sub"]}
