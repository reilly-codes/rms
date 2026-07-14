from fastapi import APIRouter, status, HTTPException, Response, Request

from app.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    set_auth_cookies,
    set_access_cookie,
    clear_auth_cookies,
    issue_access_token_from_refresh,
)
from app.schemas.user import LoginRequest, UserPublic
from app.db import SessionDep

router = APIRouter(
    prefix="/token",
    tags=["Tokens"]
)

@router.post("/", response_model=UserPublic)
async def login_for_access_token(
    login_data: LoginRequest,
    session: SessionDep,
    response: Response,
):
    user = authenticate_user(session, login_data.email, login_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect Login details",
        )

    token_payload = {"sub": user.id, "role_id": user.role_id}
    access_token = create_access_token(data=token_payload)
    refresh_token = create_refresh_token(data=token_payload)

    set_auth_cookies(response, access_token, refresh_token)

    return user

@router.post("/refresh", response_model=UserPublic)
async def refresh_access_token(
    request: Request,
    session: SessionDep,
    response: Response,
):
    new_access_token, user = issue_access_token_from_refresh(request, session)

    # Refresh cookie is left untouched here — it keeps its own 24h lifetime
    # from login, independent of how many times the access token gets renewed.
    set_access_cookie(response, new_access_token)

    return user

@router.post("/logout")
async def logout(response: Response):
    clear_auth_cookies(response)
    return {"message": "Logged out successfully"}
