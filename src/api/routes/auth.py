from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from src.db.connection import get_pool
from src.api.auth import verify_password, create_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    role: str
    username: str


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, username, password_hash, role, is_active FROM dashboard_users WHERE username = $1",
        req.username,
    )
    if not row or not row["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not verify_password(req.password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    await pool.execute("UPDATE dashboard_users SET last_login_at = NOW() WHERE id = $1", row["id"])
    token = create_token(row["username"], row["role"])
    return LoginResponse(token=token, role=row["role"], username=row["username"])
