import asyncio
import time
from datetime import datetime
from typing import Any, Literal, Optional
from urllib.parse import urlencode

import pydantic
from aiohttp import ClientSession
from sqlalchemy import CursorResult, delete
from sqlmodel import Session, col, select

from app.internal.env_settings import Settings
from app.internal.models import BookRequest
from app.util.log import logger

REFETCH_TTL = 60 * 60 * 24 * 7  # 1 week

audible_region_type = Literal[
    "us",
    "ca",
    "uk",
    "au",
    "fr",
    "de",
    "jp",
    "it",
    "in",
    "es",
    "br",
]
audible_regions: dict[audible_region_type, str] = {
    "us": ".com",
    "ca": ".ca",
    "uk": ".co.uk",
    "au": ".com.au",
    "fr": ".fr",
    "de": ".de",
    "jp": ".co.jp",
    "it": ".it",
    "in": ".in",
    "es": ".es",
    "br": ".com.br",
}


def clear_old_book_caches(session: Session):
    """Deletes outdated BookRequest entries that are used as a search result cache."""
    delete_query = delete(BookRequest).where(
        col(BookRequest.updated_at) < datetime.fromtimestamp(time.time() - REFETCH_TTL),
        col(BookRequest.user_username).is_(None),
    )
    result: CursorResult = session.execute(delete_query)  # type: ignore[reportDeprecated]
    session.commit()
    logger.debug("Cleared old book caches", rowcount=result.rowcount)


def get_region_from_settings() -> audible_region_type:
    region = Settings().app.default_region
    if region not in audible_regions:
        return "us"
    return region


async def _get_audnexus_book(
    session: ClientSession,
    asin: str,
    region: audible_region_type,
) -> Optional[BookRequest]:
    """
    https://audnex.us/#tag/Books/operation/getBookById
    """
    logger.debug("Fetching book from Audnexus", asin=asin, region=region)
    try:
        async with session.get(
            f"https://api.audnex.us/books/{asin}?region={region}",
            headers={"Client-Agent": "audiobookrequest"},
        ) as response:
            if not response.ok:
                logger.warning(
                    "Failed to fetch book from Audnexus",
                    asin=asin,
                    status=response.status,
                    reason=response.reason,
                )
                return None
            book = await response.json()
    except Exception as e:
        logger.error("Exception while fetching book from Audnexus", asin=asin, error=e)
        return None
    return BookRequest(
        asin=book["asin"],
        title=book["title"],
        subtitle=book.get("subtitle"),
        authors=[author["name"] for author in book["authors"]],
        narrators=[narrator["name"] for narrator in book["narrators"]],
        cover_image=book.get("image"),
        release_date=datetime.fromisoformat(book["releaseDate"]),
        runtime_length_min=book["runtimeLengthMin"],
    )


async def _get_audimeta_book(
    session: ClientSession,
    asin: str,
    region: audible_region_type,
) -> Optional[BookRequest]:
    """
    https://audimeta.de/api-docs/#/book/get_book__asin_
    """
    logger.debug("Fetching book from Audimeta", asin=asin, region=region)
    try:
        async with session.get(
            f"https://audimeta.de/book/{asin}?region={region}",
            headers={"Client-Agent": "audiobookrequest"},
        ) as response:
            if not response.ok:
                logger.warning(
                    "Failed to fetch book from Audimeta",
                    asin=asin,
                    status=response.status,
                    reason=response.reason,
                )
                return None
            book = await response.json()
    except Exception as e:
        logger.error("Exception while fetching book from Audimeta", asin=asin, error=e)
        return None
    return BookRequest(
        asin=book["asin"],
        title=book["title"],
        subtitle=book.get("subtitle"),
        authors=[author["name"] for author in book["authors"]],
        narrators=[narrator["name"] for narrator in book["narrators"]],
        cover_image=book.get("imageUrl"),
        release_date=datetime.fromisoformat(book["releaseDate"]),
        runtime_length_min=book["lengthMinutes"] or 0,
    )


async def get_book_by_asin(
    session: ClientSession,
    asin: str,
    audible_region: audible_region_type = get_region_from_settings(),
) -> Optional[BookRequest]:
    book = await _get_audimeta_book(session, asin, audible_region)
    if book:
        return book
    logger.debug(
        "Audimeta did not have the book, trying Audnexus",
        asin=asin,
        region=audible_region,
    )
    book = await _get_audnexus_book(session, asin, audible_region)
    if book:
        return book
    logger.warning(
        "Did not find the book on both Audnexus and Audimeta",
        asin=asin,
        region=audible_region,
    )


class CacheQuery(pydantic.BaseModel, frozen=True):
    query: str
    num_results: int
    page: int
    audible_region: audible_region_type


class CacheResult[T](pydantic.BaseModel, frozen=True):
    value: T
    timestamp: float


# simple caching of search results to avoid having to fetch from audible so frequently
search_cache: dict[CacheQuery, CacheResult[list[BookRequest]]] = {}
search_suggestions_cache: dict[str, CacheResult[list[str]]] = {}


async def get_search_suggestions(
    client_session: ClientSession,
    query: str,
    audible_region: audible_region_type = get_region_from_settings(),
) -> list[str]:
    cache_result = search_suggestions_cache.get(query)
    if cache_result and time.time() - cache_result.timestamp < REFETCH_TTL:
        return cache_result.value

    params = {
        "key_strokes": query,
        "site_variant": "desktop",
    }
    base_url = (
        f"https://api.audible{audible_regions[audible_region]}/1.0/searchsuggestions?"
    )
    url = base_url + urlencode(params)

    async with client_session.get(url) as response:
        response.raise_for_status()
        results = await response.json()

    items: list[Any] = results.get("model", {}).get("items", [])
    titles: list[str] = [
        item["model"]["product_metadata"]["title"]["value"]
        for item in items
        if item.get("model", {})
        .get("product_metadata", {})
        .get("title", {})
        .get("value")
    ]

    search_suggestions_cache[query] = CacheResult(
        value=titles,
        timestamp=time.time(),
    )

    return titles


async def list_popular_audible_books(
    session: Session,
    client_session: ClientSession,
    num_results: int = 20,
    audible_region: audible_region_type = get_region_from_settings(),
) -> list[BookRequest]:
    """
    Get popular/trending books by searching for popular terms.
    Uses the existing search functionality with popular keywords.
    """
    from pydantic import BaseModel
    
    # Create a proper cache key object
    class PopularBooksCache(BaseModel, frozen=True):
        type: str = "popular"
        region: str
        num_results: int
    
    cache_key = PopularBooksCache(region=audible_region, num_results=num_results)
    cache_result = search_cache.get(cache_key)

    if cache_result and time.time() - cache_result.timestamp < REFETCH_TTL:
        for book in cache_result.value:
            session.add(book)
        logger.debug("Using cached popular books", region=audible_region)
        return cache_result.value

    # Use popular search terms to find trending books
    popular_search_terms = [
        "bestseller",
        "james clear", 
        "atomic habits",
        "stephen king",
        "psychology", 
        "biography",
        "business",
        "self help"
    ]
    
    all_books = []
    books_per_term = max(1, num_results // len(popular_search_terms))
    
    for term in popular_search_terms:
        try:
            # Use the existing search function
            term_books = await list_audible_books(
                session=session,
                client_session=client_session,
                query=term,
                num_results=books_per_term,
                page=0,
                audible_region=audible_region
            )
            
            # Add unique books only
            for book in term_books:
                if book not in all_books and len(all_books) < num_results:
                    all_books.append(book)
                    
            if len(all_books) >= num_results:
                break
                
        except Exception as e:
            logger.warning(f"Failed to search for popular term '{term}': {e}")
            continue
    
    # Cache the results
    search_cache[cache_key] = CacheResult(
        value=all_books,
        timestamp=time.time(),
    )
    
    logger.info(f"Fetched {len(all_books)} popular books using search terms")
    return all_books


class SimilarBooksCache(pydantic.BaseModel, frozen=True):
    asin: str
    num_results: int
    audible_region: audible_region_type


async def list_similar_audible_books(
    session: Session,
    client_session: ClientSession,
    asin: str,
    num_results: int = 20,
    audible_region: audible_region_type = get_region_from_settings(),
) -> list[BookRequest]:
    """
    Fetch similar/recommended books for a given ASIN using Audible's sims endpoint when available.
    Falls back to author-based search if the endpoint fails or is unavailable.

    Ordering of returned list should match Audible's ordering where possible.
    """
    cache_key = SimilarBooksCache(asin=asin, num_results=num_results, audible_region=audible_region)
    cache_result = search_cache.get(cache_key)
    if cache_result and time.time() - cache_result.timestamp < REFETCH_TTL:
        for book in cache_result.value:
            session.add(book)
        logger.debug("Using cached sims result", asin=asin, region=audible_region)
        return cache_result.value

    base_url = f"https://api.audible{audible_regions[audible_region]}/1.0/catalog/products/{asin}/sims"
    params = {
        "num_results": str(min(50, max(1, num_results))),
        # Keep response light; details fetched via Audimeta/Audnexus
    }

    ordered: list[BookRequest] = []
    try:
        async with client_session.get(base_url, params=params) as response:
            response.raise_for_status()
            data = await response.json()

        products = data.get("products") or []
        # Extract ASINs in Audible-provided order
        asins = [p.get("asin") for p in products if p.get("asin")]
        if not asins:
            raise ValueError("No sims returned")

        # Reuse existing books from DB cache; then fetch missing via Audimeta/Audnexus
        books_map = get_existing_books(session, set(asins))
        missing_asins = [a for a in asins if a not in books_map]

        coros = [get_book_by_asin(client_session, a, audible_region) for a in missing_asins]
        fetched = await asyncio.gather(*coros)
        for b in fetched:
            if b:
                books_map[b.asin] = b

        store_new_books(session, [b for b in fetched if b])

        for a in asins:
            b = books_map.get(a)
            if b:
                ordered.append(b)

        # Trim to requested size
        ordered = ordered[:num_results]

    except Exception as e:
        # Fallback: approximate with author-based search
        logger.debug("Sims endpoint failed, falling back to author search", asin=asin, error=str(e))
        try:
            # Find seed book to derive authors
            seed = await get_book_by_asin(client_session, asin, audible_region)
            if seed:
                author = seed.authors[0] if seed.authors else seed.title
                results = await list_audible_books(
                    session=session,
                    client_session=client_session,
                    query=author,
                    num_results=num_results,
                    page=0,
                    audible_region=audible_region,
                )
                # Exclude the seed asin itself
                ordered = [b for b in results if b.asin != asin][:num_results]
            else:
                ordered = []
        except Exception:
            ordered = []

    search_cache[cache_key] = CacheResult(value=ordered, timestamp=time.time())
    return ordered


async def list_audible_books(
    session: Session,
    client_session: ClientSession,
    query: str,
    num_results: int = 20,
    page: int = 0,
    audible_region: audible_region_type = get_region_from_settings(),
) -> list[BookRequest]:
    """
    https://audible.readthedocs.io/en/latest/misc/external_api.html#get--1.0-catalog-products

    We first use the audible search API to get a list of matching ASINs. Using these ASINs we check our database
    if we have any of the books already to save on the amount of requests we have to do.
    Any books we don't already have locally, we fetch all the details from audnexus.
    """
    cache_key = CacheQuery(
        query=query,
        num_results=num_results,
        page=page,
        audible_region=audible_region,
    )
    cache_result = search_cache.get(cache_key)

    if cache_result and time.time() - cache_result.timestamp < REFETCH_TTL:
        for book in cache_result.value:
            # add back books to the session so we can access their attributes
            session.add(book)
        logger.debug("Using cached search result", query=query, region=audible_region)
        return cache_result.value

    params = {
        "num_results": num_results,
        "products_sort_by": "Relevance",
        "keywords": query,
        "page": page,
    }
    base_url = (
        f"https://api.audible{audible_regions[audible_region]}/1.0/catalog/products?"
    )
    url = base_url + urlencode(params)

    async with client_session.get(url) as response:
        response.raise_for_status()
        books_json = await response.json()

    # do not fetch book results we already have locally
    asins = set(asin_obj["asin"] for asin_obj in books_json["products"])
    books = get_existing_books(session, asins)
    for key in books.keys():
        asins.remove(key)

    # book ASINs we do not have => fetch and store
    coros = [get_book_by_asin(client_session, asin, audible_region) for asin in asins]
    new_books = await asyncio.gather(*coros)
    new_books = [b for b in new_books if b]

    store_new_books(session, new_books)

    for b in new_books:
        books[b.asin] = b

    ordered: list[BookRequest] = []
    for asin_obj in books_json["products"]:
        book = books.get(asin_obj["asin"])
        if book:
            ordered.append(book)

    # Attempt to mark items as downloaded if they exist in Audiobookshelf
    try:
        from app.internal.audiobookshelf.config import abs_config
        from app.internal.audiobookshelf.client import abs_mark_downloaded_flags

        if abs_config.is_valid(session) and abs_config.get_check_downloaded(session):
            await abs_mark_downloaded_flags(session, client_session, ordered)
    except Exception as e:
        logger.debug("ABS integration check failed", error=str(e))

    search_cache[cache_key] = CacheResult(
        value=ordered,
        timestamp=time.time(),
    )

    # clean up cache slightly
    for k in list(search_cache.keys()):
        if time.time() - search_cache[k].timestamp > REFETCH_TTL:
            try:
                del search_cache[k]
            except KeyError:  # ignore in race conditions
                pass

    return ordered


def get_existing_books(session: Session, asins: set[str]) -> dict[str, BookRequest]:
    books = list(
        session.exec(
            select(BookRequest).where(
                col(BookRequest.asin).in_(asins),
            )
        ).all()
    )

    ok_books: list[BookRequest] = []
    for b in books:
        if b.updated_at.timestamp() + REFETCH_TTL < time.time():
            continue
        ok_books.append(b)

    return {b.asin: b for b in ok_books}


def store_new_books(session: Session, books: list[BookRequest]):
    assert all(b.user_username is None for b in books)
    asins = {b.asin: b for b in books}

    existing = list(
        session.exec(
            select(BookRequest).where(
                col(BookRequest.asin).in_(asins.keys()),
                col(BookRequest.user_username).is_(None),
            )
        ).all()
    )

    to_update: list[BookRequest] = []
    for b in existing:
        new_book = asins[b.asin]
        b.title = new_book.title
        b.subtitle = new_book.subtitle
        b.authors = new_book.authors
        b.narrators = new_book.narrators
        b.cover_image = new_book.cover_image
        b.release_date = new_book.release_date
        b.runtime_length_min = new_book.runtime_length_min
        to_update.append(b)

    existing_asins = {b.asin for b in existing}
    to_add = [b for b in books if b.asin not in existing_asins]

    logger.info(
        "Storing new search results in BookRequest cache/db",
        to_add_count=len(to_add),
        to_update_count=len(to_update),
        existing_count=len(existing),
    )

    session.add_all(to_add + existing)
    session.commit()
