# app/routers/auth.py
from fastapi import APIRouter, status, HTTPException, Response, Request, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import (
    set_auth_cookies,
    set_access_cookie,
    clear_auth_cookies,
)
from app.services.auth_service import (
    AuthService,
    issue_access_token_from_refresh,
    get_current_active_user,
)
from app.schemas.user import LoginRequest, UserPublic, PasswordChange
from app.models.user import User

router = APIRouter(
    prefix="/token",
    tags=["Tokens"]
)

@router.post("/", response_model=UserPublic)
async def login_for_access_token(
    login_data: LoginRequest,
    response: Response,
    session: Session = Depends(get_session)
):
    user = AuthService.authenticate_user(session, login_data.email, login_data.password)

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
    response: Response,
    session: Session = Depends(get_session)
):
    new_access_token, user = issue_access_token_from_refresh(request, session)
    set_access_cookie(response, new_access_token)
    return user

@router.post("/logout")
async def logout(response: Response):
    clear_auth_cookies(response)
    return {"message": "Logged out successfully"}

@router.post("/change-password")
async def update_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    return AuthService.change_password(session, current_user, password_data)