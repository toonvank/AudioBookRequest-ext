from fastapi import APIRouter

from app.routers.settings.account import router as account_router
from app.routers.settings.download import router as download_router
from app.routers.settings.indexers import router as indexers_router
from app.routers.settings.notification import router as notification_router
from app.routers.settings.prowlarr import router as prowlarr_router
from app.routers.settings.audiobookshelf import router as abs_router
from app.routers.settings.security import router as security_router
from app.routers.settings.users import router as users_router
from app.routers.settings.ai import router as ai_router


router = APIRouter(prefix="/settings")

router.include_router(account_router)
router.include_router(download_router)
router.include_router(indexers_router)
router.include_router(notification_router)
router.include_router(prowlarr_router)
router.include_router(abs_router)
router.include_router(security_router)
router.include_router(users_router)
router.include_router(ai_router)
