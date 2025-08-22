from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Security
from sqlmodel import Session, select

from app.internal.auth.authentication import (
    ABRAuth,
    DetailedUser,
    create_user,
    raise_for_invalid_password,
)
from app.internal.auth.config import auth_config
from app.internal.auth.login_types import LoginTypeEnum
from app.internal.models import GroupEnum, User
from app.util.db import get_session
from app.util.templates import template_response
from app.util.toast import ToastException

router = APIRouter(prefix="/users")


@router.get("/")
def read_users(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    users = session.exec(select(User)).all()
    is_oidc = auth_config.get_login_type(session) == LoginTypeEnum.oidc
    return template_response(
        "settings_page/users.html",
        request,
        admin_user,
        {
            "page": "users",
            "users": users,
            "is_oidc": is_oidc,
        },
    )


@router.post("/")
def create_new_user(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    group: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    if username.strip() == "":
        raise ToastException("Invalid username", "error")

    try:
        raise_for_invalid_password(session, password, ignore_confirm=True)
    except HTTPException as e:
        raise ToastException(e.detail, "error")

    if group not in GroupEnum.__members__:
        raise ToastException("Invalid group selected", "error")

    group = GroupEnum[group]

    user = session.exec(select(User).where(User.username == username)).first()
    if user:
        raise ToastException("Username already exists", "error")

    user = create_user(username, password, group)
    session.add(user)
    session.commit()

    users = session.exec(select(User)).all()

    return template_response(
        "settings_page/users.html",
        request,
        admin_user,
        {"users": users, "success": "Created user"},
        block_name="user_block",
    )


@router.delete("/{username}")
def delete_user(
    request: Request,
    username: str,
    session: Annotated[Session, Depends(get_session)],
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    if username == admin_user.username:
        raise ToastException("Cannot delete own user", "error")

    user = session.exec(select(User).where(User.username == username)).one_or_none()
    if user and user.root:
        raise ToastException("Cannot delete root user", "error")

    if user:
        session.delete(user)
        session.commit()

    users = session.exec(select(User)).all()

    return template_response(
        "settings_page/users.html",
        request,
        admin_user,
        {"users": users, "success": "Deleted user"},
        block_name="user_block",
    )


@router.patch("/{username}")
def update_user(
    request: Request,
    username: str,
    group: Annotated[GroupEnum, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    user = session.exec(select(User).where(User.username == username)).one_or_none()
    if user and user.root:
        raise ToastException("Cannot change root user's group", "error")

    if user:
        user.group = group
        session.add(user)
        session.commit()

    users = session.exec(select(User)).all()
    return template_response(
        "settings_page/users.html",
        request,
        admin_user,
        {"users": users, "success": "Updated user"},
        block_name="user_block",
    )
