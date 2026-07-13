from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from pb_api.api.deps import CurrentUser, SessionDep, require_roles
from pb_api.db.models.user import UserRole
from pb_api.schemas.user import UserList, UserRead
from pb_api.services import users as user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def read_current_user(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.get(
    "",
    response_model=UserList,
    dependencies=[require_roles(UserRole.ADMIN)],
    summary="List users (admin only)",
)
async def list_users(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserList:
    items, total = await user_service.list_users(session, limit=limit, offset=offset)
    return UserList(
        items=[UserRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
