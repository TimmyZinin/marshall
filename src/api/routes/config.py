from fastapi import APIRouter, Depends
from src.api.config import DEMO_MODE
from src.api.auth import get_current_user

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def get_config(_user: dict = Depends(get_current_user)):
    return {"demo_mode": DEMO_MODE}
