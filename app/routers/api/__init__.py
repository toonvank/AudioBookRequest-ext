from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlmodel import Session, select, text

from app.routers.api.indexers import router as indexers_router
from app.routers.api.users import router as users_router
from app.routers.api.recommendations import router as recommendations_router
from app.util.db import get_session
from app.util.log import logger

router = APIRouter(prefix="/api", tags=["API"])
router.include_router(indexers_router)
router.include_router(users_router)
router.include_router(recommendations_router)


@router.get("/health", tags=["System"])
def health_check(session: Annotated[Session, Depends(get_session)]):
    try:
        session.exec(select(text("1"))).one()
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return Response(status_code=500)
    return Response(status_code=200)
