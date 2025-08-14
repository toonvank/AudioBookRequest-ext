import json
from typing import Optional

from aiohttp import ClientSession
from sqlmodel import Session, select

from app.internal.models import (
    BookRequest,
    EventEnum,
    ManualBookRequest,
    Notification,
    NotificationBodyTypeEnum,
)
from app.util import json_type
from app.util.db import open_session
from app.util.log import logger


def replace_variables(
    template: str,
    username: Optional[str] = None,
    book_title: Optional[str] = None,
    book_authors: Optional[str] = None,
    book_narrators: Optional[str] = None,
    event_type: Optional[str] = None,
    other_replacements: dict[str, str] = {},
):
    if username:
        template = template.replace("{eventUser}", username)
    if book_title:
        template = template.replace("{bookTitle}", book_title)
    if book_authors:
        template = template.replace("{bookAuthors}", book_authors)
    if book_narrators:
        template = template.replace("{bookNarrators}", book_narrators)
    if event_type:
        template = template.replace("{eventType}", event_type)

    for key, value in other_replacements.items():
        template = template.replace(f"{{{key}}}", value)

    return template


async def _send(
    body: str | dict[str, json_type.JSON],
    notification: Notification,
    client_session: ClientSession,
):
    if notification.body_type == NotificationBodyTypeEnum.json:
        async with client_session.post(
            notification.url,
            json=body,
            headers=notification.headers,
        ) as response:
            response.raise_for_status()
            return await response.text()
    elif notification.body_type == NotificationBodyTypeEnum.text:
        async with client_session.post(
            notification.url,
            data=body,
            headers=notification.headers,
        ) as response:
            response.raise_for_status()
            return await response.text()


async def send_notification(
    session: Session,
    notification: Notification,
    requester_username: Optional[str] = None,
    book_asin: Optional[str] = None,
    other_replacements: dict[str, str] = {},
):
    book_title = None
    book_authors = None
    book_narrators = None
    if book_asin:
        book = session.exec(
            select(BookRequest).where(BookRequest.asin == book_asin)
        ).first()
        if book:
            book_title = book.title
            book_authors = ",".join(book.authors)
            book_narrators = ",".join(book.narrators)

    body = replace_variables(
        notification.body,
        requester_username,
        book_title,
        book_authors,
        book_narrators,
        notification.event.value,
        other_replacements,
    )

    if notification.body_type == NotificationBodyTypeEnum.json:
        body = json.loads(body, strict=False)

    logger.info(
        "Sending notification",
        url=notification.url,
        body=body,
        event_type=notification.event.value,
        body_type=notification.body_type.value,
        headers=notification.headers,
    )

    try:
        async with ClientSession() as client_session:
            resp = await _send(body, notification, client_session)
        logger.info(
            "Notification sent successfully",
            url=notification.url,
            response=resp,
        )
        return resp
    except Exception as e:
        logger.error(
            "Failed to send notification",
            url=notification.url,
            body=body,
            error=str(e),
        )
        raise


async def send_all_notifications(
    event_type: EventEnum,
    requester_username: Optional[str] = None,
    book_asin: Optional[str] = None,
    other_replacements: dict[str, str] = {},
):
    with open_session() as session:
        notifications = session.exec(
            select(Notification).where(
                Notification.event == event_type, Notification.enabled
            )
        ).all()
        for notification in notifications:
            await send_notification(
                session=session,
                notification=notification,
                requester_username=requester_username,
                book_asin=book_asin,
                other_replacements=other_replacements,
            )


async def send_manual_notification(
    notification: Notification,
    book: ManualBookRequest,
    requester_username: Optional[str] = None,
    other_replacements: dict[str, str] = {},
):
    """Send a notification for manual book requests"""
    try:
        book_authors = ",".join(book.authors)
        book_narrators = ",".join(book.narrators)

        body = replace_variables(
            notification.body,
            requester_username,
            book.title,
            book_authors,
            book_narrators,
            notification.event.value,
            other_replacements,
        )

        if notification.body_type == NotificationBodyTypeEnum.json:
            body = json.loads(body)

        logger.info(
            "Sending manual notification",
            url=notification.url,
            body=body,
            event_type=notification.event.value,
            body_type=notification.body_type.value,
            headers=notification.headers,
        )

        async with ClientSession() as client_session:
            return await _send(body, notification, client_session)

    except Exception as e:
        logger.error("Failed to send notification", error=str(e))
        return None


async def send_all_manual_notifications(
    event_type: EventEnum,
    book_request: ManualBookRequest,
    other_replacements: dict[str, str] = {},
):
    with open_session() as session:
        notifications = session.exec(
            select(Notification).where(
                Notification.event == event_type, Notification.enabled
            )
        ).all()
        for notif in notifications:
            await send_manual_notification(
                notification=notif,
                book=book_request,
                requester_username=book_request.user_username,
                other_replacements=other_replacements,
            )
