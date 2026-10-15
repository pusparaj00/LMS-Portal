from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import get_engine, get_redis
from app.schemas import HealthResponse

router = APIRouter()


def _database_ok() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _redis_ok() -> bool:
    try:
        return bool(get_redis().ping())
    except Exception:
        return False


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health():
    db, redis_ = _database_ok(), _redis_ok()
    body = HealthResponse(
        status="ok" if db and redis_ else "degraded",
        database="ok" if db else "down",
        redis="ok" if redis_ else "down",
    )
    return JSONResponse(status_code=200 if body.status == "ok" else 503, content=body.model_dump())
