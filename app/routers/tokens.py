from fastapi import APIRouter, status, HTTPException
from datetime import timedelta

from app.schemas.token import Token
from app.auth import authenticate_user, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from app.schemas.user import LoginRequest
from app.db import SessionDep

router = APIRouter(
    prefix="/token",
    tags=["Tokens"]
)

@router.post("/", response_model=Token)
async def login_for_access_token(
    login_data: LoginRequest,
    session: SessionDep
):
    user = authenticate_user(session, login_data.email, login_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect Login details",
            headers={"WWW-Authenticate" : "Bearer"},
        )
    
    access_token_expiry = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub" : user.id,
            "role_id" : user.role_id
        },
        expires_delta=access_token_expiry
    )

    return Token(access_token=access_token, token_type="bearer")