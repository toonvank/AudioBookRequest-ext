from __future__ import annotations

import asyncio
import posixpath
import re
from typing import Any, Optional

from aiohttp import ClientSession
from sqlmodel import Session

from app.internal.audiobookshelf.config import abs_config
from app.internal.models import BookRequest
from app.util.log import logger


def _headers(session: Session) -> dict[str, str]:
    token = abs_config.get_api_token(session)
    assert token is not None
    return {"Authorization": f"Bearer {token}"}


async def abs_get_libraries(
    session: Session, client_session: ClientSession
) -> list[dict[str, Any]]:
    base_url = abs_config.get_base_url(session)
    if not base_url:
        return []
    url = posixpath.join(base_url, "api/libraries")
    async with client_session.get(url, headers=_headers(session)) as resp:
        if not resp.ok:
            logger.error(
                "ABS: failed to fetch libraries", status=resp.status, reason=resp.reason
            )
            return []
        data = await resp.json()
        # response shape: { libraries: [...] }
        libs = data.get("libraries") or []
        return libs


async def abs_trigger_scan(session: Session, client_session: ClientSession) -> bool:
    base_url = abs_config.get_base_url(session)
    lib_id = abs_config.get_library_id(session)
    if not base_url or not lib_id:
        return False
    url = posixpath.join(base_url, f"api/libraries/{lib_id}/scan")
    async with client_session.post(url, headers=_headers(session), json={}) as resp:
        if not resp.ok:
            logger.warning(
                "ABS: failed to trigger scan", status=resp.status, reason=resp.reason
            )
            return False
        return True


def _normalize(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


async def _abs_search(session: Session, client_session: ClientSession, q: str) -> list[dict[str, Any]]:
    base_url = abs_config.get_base_url(session)
    lib_id = abs_config.get_library_id(session)
    if not base_url or not lib_id:
        return []
    url = posixpath.join(base_url, f"api/libraries/{lib_id}/search")
    async with client_session.get(url, headers=_headers(session), params={"q": q}) as resp:
        if not resp.ok:
            logger.debug("ABS: search failed", status=resp.status, reason=resp.reason)
            return []
        data = await resp.json()
        # response shape: { results: [ { libraryItem: {...}, media: {...}} ] } in newer ABS
        items = data.get("results") or data.get("items") or []
        return items


async def abs_book_exists(
    session: Session, client_session: ClientSession, book: BookRequest
) -> bool:
    """
    Heuristic check if a book exists in ABS library by searching by ASIN and title/author.
    """
    # Try ASIN first
    candidates: list[dict[str, Any]] = []
    if book.asin:
        candidates = await _abs_search(session, client_session, book.asin)
    if not candidates:
        # Try title search with first author
        author = book.authors[0] if book.authors else ""
        q = f"{book.title} {author}".strip()
        candidates = await _abs_search(session, client_session, q)

    if not candidates:
        return False

    norm_title = _normalize(book.title)
    norm_authors = {_normalize(a) for a in book.authors}

    for it in candidates:
        # ABS search returns different shapes, try best-effort
        media = it.get("media") or it.get("book") or {}
        title = media.get("title") or it.get("title") or ""
        authors = media.get("authors") or media.get("authorName") or []
        if isinstance(authors, str):
            authors = [authors]
        if _normalize(title) == norm_title:
            if not norm_authors or any(_normalize(a) in norm_authors for a in authors):
                return True
    return False


async def abs_mark_downloaded_flags(
    session: Session, client_session: ClientSession, books: list[BookRequest]
) -> None:
    if not abs_config.get_check_downloaded(session):
        return
    # Only check books not already marked downloaded
    to_check = [b for b in books if not b.downloaded]
    # Limit to avoid flooding ABS
    to_check = to_check[:25]

    async def _check_and_mark(b: BookRequest):
        try:
            exists = await abs_book_exists(session, client_session, b)
            if exists:
                b.downloaded = True
                session.add(b)
        except Exception as e:
            logger.debug("ABS: failed exist check", asin=b.asin, error=str(e))

    await asyncio.gather(*[_check_and_mark(b) for b in to_check])
    session.commit()
