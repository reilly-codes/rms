import os
import jwt

from fastapi import Depends, HTTPException, status, Request
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from typing import Annotated
from uuid import UUID
from datetime import timedelta, datetime, timezone
from dotenv import load_dotenv
from sqlmodel import Session, select

from app.db import get_session
from app.models.user import User
from app.schemas.token import TokenData
from app.schemas.user import PasswordChange, ResetPassword


load_dotenv()
JWT_SECRET_KEY=os.getenv("JWT_SECRET_KEY")
ALGORITHM="HS256"

# Access token (short-lived, used on every request) vs refresh token
# (longer-lived, only used to mint new access tokens).
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12   # 12 hours
REFRESH_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

ACCESS_COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"

# Cookies must be marked secure (HTTPS-only) in production, but that breaks
# local http://localhost dev. Toggle based on ENVIRONMENT, same pattern db.py uses.
COOKIE_SECURE = os.getenv("ENVIRONMENT", "development") == "production"

password_hash = PasswordHash.recommended()

def verify_password(plain_txt_password, hashed_password):
    return password_hash.verify(plain_txt_password, hashed_password)

def get_password_hash(plain_txt_password):
    return password_hash.hash(plain_txt_password)

    
def authenticate_user(session: Session, email: str, plain_txt_password: str):
    statement = select(User).where(User.email == email)
    user = session.exec(statement).first()

    if not user:
        return False
    if not verify_password(plain_txt_password, user.hashed_password):
        return False
    
    return user

def _create_token(data: dict, expires_delta: timedelta, token_type: str):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta

    if "sub" in to_encode and isinstance(to_encode["sub"], UUID):
        to_encode["sub"] = str(to_encode["sub"])

    to_encode.update({"exp": expire, "type": token_type})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    return _create_token(data, expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES), "access")

def create_refresh_token(data: dict, expires_delta: timedelta | None = None):
    return _create_token(data, expires_delta or timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES), "refresh")

def set_access_cookie(response, access_token: str):
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",  # flip it: "none" in dev, "lax" in prod
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )

def set_refresh_cookie(response, refresh_token: str):
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",  # flip it here too
        max_age=REFRESH_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )

def set_auth_cookies(response, access_token: str, refresh_token: str):
    set_access_cookie(response, access_token)
    set_refresh_cookie(response, refresh_token)

def clear_auth_cookies(response):
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/")

def _decode_token(token: str, expected_type: str):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != expected_type:
            raise credentials_exception
        return payload
    except (InvalidTokenError, ValueError):
        raise credentials_exception

async def get_current_user(request: Request, session: Session = Depends(get_session)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        raise credentials_exception

    payload = _decode_token(token, "access")
    usr_id = payload.get("sub")
    usr_role = payload.get("role_id")
    if usr_id is None or usr_role is None:
        raise credentials_exception
    token_data = TokenData(id=usr_id, role_id=usr_role)
    
    user = session.get(User, token_data.id)

    if user is None:
        raise credentials_exception
    
    return user

async def get_current_active_user(current_user: Annotated[User, Depends(get_current_user)],):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive User")
    
    return current_user

def issue_access_token_from_refresh(request: Request, session: Session) -> tuple[str, User]:
    """Validates the refresh_token cookie and returns a freshly minted access token + the user."""
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token provided")

    payload = _decode_token(refresh_token, "refresh")
    usr_id = payload.get("sub")
    usr_role = payload.get("role_id")
    if usr_id is None or usr_role is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = session.get(User, UUID(usr_id))
    if user is None or user.disabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer valid")

    new_access_token = create_access_token(data={"sub": user.id, "role_id": user.role_id})
    return new_access_token, user

async def change_password(
    password_data: PasswordChange,
    current_user: User,
    session: Session
):
    if password_data.new_password != password_data.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New passwords do not match")
    
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")
    
    if verify_password(password_data.new_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New Password must be different from current password")
    
    current_user.hashed_password = get_password_hash(password_data.new_password)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    
    return {"message": "Password updated successfully"}

def create_reset_password_token(user: User):
    data = {
        "sub" : user.email,
        "exp" : datetime.now() + timedelta(minutes=10)
    }
    token = jwt.encode(data, JWT_SECRET_KEY, algorithm=ALGORITHM)
    
    return token

async def reset_password(
    reset_data: ResetPassword,
    session: Session 
):
    try:
        payload = jwt.decode(reset_data.secret_token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token has expired")
        
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid Token")
    
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User could not be found")
    
    if reset_data.new_password != reset_data.confirm_password:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="New Password and confirm password must be same")
    
    qry = select(User).where(User.email == email)
    user = session.exec(qry).first()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User could not be found")
    
    hashed_password = get_password_hash(reset_data.new_password)
    user.hashed_password = hashed_password
    session.add(user)
    session.commit()
    session.refresh(user)
    
    return {"message" :  "Password reset successfully", "succes" : True, "status_code" : status.HTTP_200_OK}