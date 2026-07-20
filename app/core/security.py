# app/core/security.py
import jwt
from uuid import UUID
from datetime import datetime, timedelta, timezone
from pwdlib import PasswordHash
from fastapi import Response, HTTPException, status
from jwt.exceptions import InvalidTokenError

from app.core.config import settings

password_hash = PasswordHash.recommended()

def verify_password(plain_txt_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_txt_password, hashed_password)

def get_password_hash(plain_txt_password: str) -> str:
    return password_hash.hash(plain_txt_password)

def _create_token(data: dict, expires_delta: timedelta, token_type: str) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta

    if "sub" in to_encode and isinstance(to_encode["sub"], UUID):
        to_encode["sub"] = str(to_encode["sub"])

    to_encode.update({"exp": expire, "type": token_type})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    expires = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return _create_token(data, expires, "access")

def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    expires = expires_delta or timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    return _create_token(data, expires, "refresh")

def decode_token(token: str, expected_type: str) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != expected_type:
            raise credentials_exception
        return payload
    except (InvalidTokenError, ValueError):
        raise credentials_exception

# Cookie Helpers
def set_access_cookie(response: Response, access_token: str):
    response.set_cookie(
        key=settings.ACCESS_COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )

def set_refresh_cookie(response: Response, refresh_token: str):
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )

def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    set_access_cookie(response, access_token)
    set_refresh_cookie(response, refresh_token)

def clear_auth_cookies(response: Response):
    response.delete_cookie(settings.ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/")