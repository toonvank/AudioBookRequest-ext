import uuid
from typing import Annotated, Optional

from aiohttp import ClientSession
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
    Security,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.internal import book_search
from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.book_search import (
    audible_region_type,
    audible_regions,
    clear_old_book_caches,
    get_book_by_asin,
    get_region_from_settings,
    list_audible_books,
)
from app.internal.models import (
    BookRequest,
    BookSearchResult,
    EventEnum,
    GroupEnum,
    ManualBookRequest,
    User,
)
from app.internal.notifications import (
    send_all_manual_notifications,
    send_all_notifications,
)
from app.internal.prowlarr.prowlarr import prowlarr_config
from app.internal.query import query_sources
from app.internal.ranking.quality import quality_config
from app.routers.wishlist import get_wishlist_books, get_wishlist_counts
from app.util.connection import get_connection
from app.util.db import get_session, open_session
from app.util.recommendations import get_homepage_recommendations
from app.util.templates import template_response

router = APIRouter(prefix="/search")


def get_already_requested(session: Session, results: list[BookRequest], username: str):
    books: list[BookSearchResult] = []
    if len(results) > 0:
        # check what books are already requested by the user
        asins = {book.asin for book in results}
        requested_books = set(
            session.exec(
                select(BookRequest.asin).where(
                    col(BookRequest.asin).in_(asins),
                    BookRequest.user_username == username,
                )
            ).all()
        )

        for book in results:
            book_search = BookSearchResult.model_validate(book)
            if book.asin in requested_books:
                book_search.already_requested = True
            books.append(book_search)
    return books


@router.get("")
async def read_search(
    request: Request,
    client_session: Annotated[ClientSession, Depends(get_connection)],
    session: Annotated[Session, Depends(get_session)],
    query: Annotated[Optional[str], Query(alias="q")] = None,
    num_results: int = 20,
    page: int = 0,
    region: audible_region_type = get_region_from_settings(),
    user: DetailedUser = Security(ABRAuth()),
):
    if audible_regions.get(region) is None:
        raise HTTPException(status_code=400, detail="Invalid region")
    if query:
        results = await list_audible_books(
            session=session,
            client_session=client_session,
            query=query,
            num_results=num_results,
            page=page,
            audible_region=region,
        )
    else:
        results = []

    books: list[BookSearchResult] = []
    if len(results) > 0:
        books = get_already_requested(session, results, user.username)

    prowlarr_configured = prowlarr_config.is_valid(session)

    clear_old_book_caches(session)
    
    # Get recommendations if no search term is provided
    recommendations = None
    if not query:
        recommendations = get_homepage_recommendations(session, user)

    return template_response(
        "search.html",
        request,
        user,
        {
            "search_term": query or "",
            "search_results": books,
            "regions": audible_regions,
            "selected_region": region,
            "page": page,
            "auto_start_download": quality_config.get_auto_download(session)
            and user.is_above(GroupEnum.trusted),
            "prowlarr_configured": prowlarr_configured,
            "recommendations": recommendations,
        },
    )


@router.get("/suggestions")
async def search_suggestions(
    request: Request,
    query: Annotated[str, Query(alias="q")],
    user: DetailedUser = Security(ABRAuth()),
    region: audible_region_type = get_region_from_settings(),
):
    async with ClientSession() as client_session:
        suggestions = await book_search.get_search_suggestions(
            client_session, query, region
        )
        return template_response(
            "search.html",
            request,
            user,
            {"suggestions": suggestions},
            block_name="search_suggestions",
        )


async def background_start_query(asin: str, requester: User, auto_download: bool):
    with open_session() as session:
        async with ClientSession() as client_session:
            await query_sources(
                asin=asin,
                session=session,
                client_session=client_session,
                start_auto_download=auto_download,
                requester=requester,
            )


@router.post("/request/{asin}")
async def add_request(
    request: Request,
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    background_task: BackgroundTasks,
    query: Annotated[Optional[str], Form()] = None,
    page: Annotated[int, Form()] = 0,
    region: Annotated[audible_region_type, Form()] = get_region_from_settings(),
    num_results: Annotated[int, Form()] = 20,
    redirect_to_home: Annotated[Optional[str], Form()] = None,
    user: DetailedUser = Security(ABRAuth()),
):
    book = await get_book_by_asin(client_session, asin, region)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    book.user_username = user.username
    try:
        session.add(book)
        session.commit()
    except IntegrityError:
        session.rollback()
        pass  # ignore if already exists

    background_task.add_task(
        send_all_notifications,
        event_type=EventEnum.on_new_request,
        requester=User.model_validate(user),
        book_asin=asin,
    )

    if quality_config.get_auto_download(session) and user.is_above(GroupEnum.trusted):
        # start querying and downloading if auto download is enabled
        background_task.add_task(
            background_start_query,
            asin=asin,
            requester=User.model_validate(user),
            auto_download=True,
        )

    # If redirect_to_home is set, redirect to homepage instead of refreshing search results
    if redirect_to_home:
        recommendations = get_homepage_recommendations(session, user)
        return template_response(
            "root.html",
            request,
            user,
            {
                "recommendations": recommendations,
            },
        )

    if audible_regions.get(region) is None:
        raise HTTPException(status_code=400, detail="Invalid region")
    if query:
        results = await list_audible_books(
            session=session,
            client_session=client_session,
            query=query,
            num_results=num_results,
            page=page,
            audible_region=region,
        )
    else:
        results = []

    books: list[BookSearchResult] = []
    if len(results) > 0:
        books = get_already_requested(session, results, user.username)

    prowlarr_configured = prowlarr_config.is_valid(session)
    
    # Get recommendations if no search term is provided
    recommendations = None
    if not query:
        recommendations = get_homepage_recommendations(session, user)

    return template_response(
        "search.html",
        request,
        user,
        {
            "search_term": query or "",
            "search_results": books,
            "regions": audible_regions,
            "selected_region": region,
            "page": page,
            "auto_start_download": quality_config.get_auto_download(session)
            and user.is_above(GroupEnum.trusted),
            "prowlarr_configured": prowlarr_configured,
            "recommendations": recommendations,
        },
        block_name="book_results",
    )


@router.delete("/request/{asin}")
async def delete_request(
    request: Request,
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    downloaded: Optional[bool] = None,
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    books = session.exec(select(BookRequest).where(BookRequest.asin == asin)).all()
    if books:
        [session.delete(b) for b in books]
        session.commit()

    books = get_wishlist_books(
        session, None, "downloaded" if downloaded else "not_downloaded"
    )
    counts = get_wishlist_counts(session, admin_user)

    return template_response(
        "wishlist_page/wishlist.html",
        request,
        admin_user,
        {
            "books": books,
            "page": "downloaded" if downloaded else "wishlist",
            "counts": counts,
            "update_tablist": True,
        },
        block_name="book_wishlist",
    )


@router.get("/manual")
async def read_manual(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    id: Optional[uuid.UUID] = None,
    user: DetailedUser = Security(ABRAuth()),
):
    book = None
    if id:
        book = session.get(ManualBookRequest, id)

    auto_download = quality_config.get_auto_download(session)
    return template_response(
        "manual.html", request, user, {"auto_download": auto_download, "book": book}
    )


@router.post("/manual")
async def add_manual(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    title: Annotated[str, Form()],
    author: Annotated[str, Form()],
    narrator: Annotated[Optional[str], Form()] = None,
    subtitle: Annotated[Optional[str], Form()] = None,
    publish_date: Annotated[Optional[str], Form()] = None,
    info: Annotated[Optional[str], Form()] = None,
    id: Optional[uuid.UUID] = None,
    user: DetailedUser = Security(ABRAuth()),
):
    if id:
        book_request = session.get(ManualBookRequest, id)
        if not book_request:
            raise HTTPException(status_code=404, detail="Book request not found")
        book_request.title = title
        book_request.subtitle = subtitle
        book_request.authors = author.split(",")
        book_request.narrators = narrator.split(",") if narrator else []
        book_request.publish_date = publish_date
        book_request.additional_info = info
    else:
        book_request = ManualBookRequest(
            user_username=user.username,
            title=title,
            authors=author.split(","),
            narrators=narrator.split(",") if narrator else [],
            subtitle=subtitle,
            publish_date=publish_date,
            additional_info=info,
        )
    session.add(book_request)
    session.commit()

    background_task.add_task(
        send_all_manual_notifications,
        event_type=EventEnum.on_new_request,
        book_request=ManualBookRequest.model_validate(book_request),
    )

    auto_download = quality_config.get_auto_download(session)

    return template_response(
        "manual.html",
        request,
        user,
        {"success": "Successfully added request", "auto_download": auto_download},
        block_name="form",
    )
