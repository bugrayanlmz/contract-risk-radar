from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.db import get_session
from app.models import User

COOKIE_NAME = "radar_session"
hasher = PasswordHasher()


def auth_error():
    return HTTPException(
        401, detail={"code": "UNAUTHENTICATED", "message": "Please sign in to continue."}
    )


def issue_token(user_id: UUID) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(hours=1),
            "iss": "contract-risk-radar",
            "aud": "radar-app",
        },
        get_settings().jwt_secret,
        algorithm="HS256",
    )


async def verify_password(password: str, encoded: str) -> bool:
    try:
        return await run_in_threadpool(hasher.verify, encoded, password)
    except VerificationError:
        return False


async def current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise auth_error()
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=["HS256"],
            audience="radar-app",
            issuer="contract-risk-radar",
            options={"require": ["sub", "exp", "iat"]},
        )
        user_id = UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise auth_error() from None
    user = await session.get(User, user_id)
    if user is None:
        raise auth_error()
    return user
