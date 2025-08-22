from typing import Annotated
from fastapi import APIRouter, Depends, Response
from sqlmodel import Session, select, text

from app.util.log import logger
from app.util.db import get_session
from app.routers.api.users import router as users_router

router = APIRouter(prefix="/api", tags=["API"])
router.include_router(users_router)


@router.get("/health", tags=["System"])
def health_check(session: Annotated[Session, Depends(get_session)]):
    try:
        session.exec(select(text("1"))).one()
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return Response(status_code=500)
    return Response(status_code=200)
