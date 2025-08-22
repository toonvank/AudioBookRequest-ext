from typing import Annotated, Any, Mapping, Optional

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Form, Request, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.indexers.abstract import SessionContainer
from app.internal.indexers.configuration import indexer_configuration_cache
from app.internal.indexers.indexer_util import IndexerContext, get_indexer_contexts
from app.internal.models import GroupEnum
from app.internal.prowlarr.prowlarr import flush_prowlarr_cache
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.templates import template_response
from app.util.toast import ToastException

router = APIRouter(prefix="/indexers")


@router.get("/")
async def read_indexers(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    contexts = await get_indexer_contexts(
        SessionContainer(session=session, client_session=client_session),
        check_required=False,
        return_disabled=True,
    )

    return template_response(
        "settings_page/indexers.html",
        request,
        admin_user,
        {
            "page": "indexers",
            "indexers": contexts,
        },
    )


async def update_single_indexer(
    indexer_select: str,
    values: Mapping[str, Any],
    session: Session,
    client_session: ClientSession,
):
    contexts = await get_indexer_contexts(
        SessionContainer(session=session, client_session=client_session),
        check_required=False,
        return_disabled=True,
    )

    updated_context: Optional[IndexerContext] = None
    for context in contexts:
        if context.indexer.name == indexer_select:
            updated_context = context
            break

    if not updated_context:
        raise ToastException("Indexer not found", "error")

    for key, context in updated_context.configuration.items():
        value = values.get(key)
        if value is None:
            # forms do not include false checkboxes, so we handle missing booleans as false
            if context.type is bool:
                value = False
            else:
                logger.warning("Value is missing for key", key=key)
                continue
        if context.type is bool:
            indexer_configuration_cache.set_bool(session, key, value == "on")
        else:
            indexer_configuration_cache.set(session, key, str(value))

    flush_prowlarr_cache()


@router.post("/")
async def update_indexers(
    request: Request,
    indexer_select: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    await update_single_indexer(
        indexer_select,
        await request.form(),
        session,
        client_session,
    )

    raise ToastException("Indexers updated", "success")
