"""Authentication endpoints: register, login, refresh.

Self-service registration always creates CLIENT users; ADMIN/STAFF accounts
are provisioned via ``python -m pb_api.cli create-admin``. Refresh tokens are
stateless in this phase — rotation is implemented, server-side revocation
lands with the session store in a later phase (tokens already carry ``jti``).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from pb_api.api.deps import SessionDep, SettingsDep
from pb_api.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from pb_api.schemas.auth import LoginRequest, RefreshRequest, TokenPair
from pb_api.schemas.user import UserCreate, UserRead
from pb_api.services import users as user_service
from pb_api.services.users import EmailAlreadyRegisteredError, WeakPasswordError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, session: SessionDep, settings: SettingsDep) -> UserRead:
    try:
        user = await user_service.create_user(
            session,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            password_min_length=settings.password_min_length,
        )
    except WeakPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email is already registered"
        ) from exc
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, session: SessionDep, settings: SettingsDep) -> TokenPair:
    user = await user_service.authenticate(session, email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenPair(
        access_token=create_access_token(
            subject=str(user.id), role=user.role.value, settings=settings
        ),
        refresh_token=create_refresh_token(subject=str(user.id), settings=settings),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, session: SessionDep, settings: SettingsDep) -> TokenPair:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh", settings=settings)
        user_id = uuid.UUID(claims["sub"])
    except (TokenError, KeyError, ValueError) as exc:
        raise invalid from exc

    user = await user_service.get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise invalid

    return TokenPair(
        access_token=create_access_token(
            subject=str(user.id), role=user.role.value, settings=settings
        ),
        refresh_token=create_refresh_token(subject=str(user.id), settings=settings),
        expires_in=settings.access_token_expire_minutes * 60,
    )
