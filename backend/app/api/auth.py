from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.db import get_session
from app.models import User
from app.schemas.responses import Credentials, UserResponse
from app.services.auth import COOKIE_NAME, current_user, hasher, issue_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def set_session(response: Response, user: User):
    response.set_cookie(
        COOKIE_NAME,
        issue_token(user.id),
        max_age=3600,
        httponly=True,
        secure=get_settings().secure_cookie,
        samesite="lax",
        path="/api",
    )


@router.post("/register", response_model=UserResponse, status_code=201, operation_id="register")
async def register(
    data: Credentials, response: Response, session: AsyncSession = Depends(get_session)
):
    user = User(
        email=str(data.email).strip().lower(),
        password_hash=await run_in_threadpool(hasher.hash, data.password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            409,
            detail={
                "code": "EMAIL_EXISTS",
                "message": "An account with this email already exists.",
            },
        ) from None
    set_session(response, user)
    return user


@router.post("/login", response_model=UserResponse, operation_id="login")
async def login(
    data: Credentials, response: Response, session: AsyncSession = Depends(get_session)
):
    user = await session.scalar(select(User).where(User.email == str(data.email).strip().lower()))
    if user is None or not await verify_password(data.password, user.password_hash):
        raise HTTPException(
            401,
            detail={"code": "INVALID_CREDENTIALS", "message": "Email or password is incorrect."},
        )
    set_session(response, user)
    return user


@router.post("/logout", status_code=204, operation_id="logout")
async def logout(response: Response):
    response.delete_cookie(
        COOKIE_NAME, path="/api", httponly=True, secure=get_settings().secure_cookie, samesite="lax"
    )


@router.get("/me", response_model=UserResponse, operation_id="getMe")
async def me(user: User = Depends(current_user)):
    return user
