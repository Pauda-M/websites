"""User domain service — all user persistence and credential logic lives here,
keeping route handlers thin and the rules testable without HTTP."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pb_api.core.security import dummy_verify, hash_password, verify_password
from pb_api.db.models.user import User, UserRole


class EmailAlreadyRegisteredError(Exception):
    pass


class WeakPasswordError(Exception):
    def __init__(self, min_length: int) -> None:
        super().__init__(f"Password must be at least {min_length} characters long")
        self.min_length = min_length


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == normalize_email(email)))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
    role: UserRole = UserRole.CLIENT,
    password_min_length: int,
) -> User:
    if len(password) < password_min_length:
        raise WeakPasswordError(password_min_length)

    normalized = normalize_email(email)
    if await get_user_by_email(session, normalized) is not None:
        raise EmailAlreadyRegisteredError(normalized)

    user = User(
        email=normalized,
        hashed_password=hash_password(password),
        full_name=full_name.strip(),
        role=role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def authenticate(session: AsyncSession, *, email: str, password: str) -> User | None:
    user = await get_user_by_email(session, email)
    if user is None:
        # Equalise response timing between unknown-user and bad-password paths.
        dummy_verify()
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


async def list_users(
    session: AsyncSession, *, limit: int = 50, offset: int = 0
) -> tuple[list[User], int]:
    total = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    result = await session.execute(
        select(User).order_by(User.created_at.desc(), User.id).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), total
