from fastapi import APIRouter

from ..models import Health

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/healthz", response_model=Health)
async def healthz() -> Health:
    return Health()
