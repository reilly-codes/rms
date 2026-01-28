import os
import jwt

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from typing import Annotated
from uuid import UUID
from datetime import timedelta, datetime, timezone
from dotenv import load_dotenv
from sqlmodel import Session, select

from db import get_session
from models import TokenData, User

load_dotenv()
JWT_SECRET_KEY=os.getenv("JWT_SECRET_KEY")
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30

password_hash = PasswordHash.recommended()
oauth2_scheme =  OAuth2PasswordBearer(tokenUrl="token")

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

def create_access_token(data: dict, expires_delta: timedelta | None  = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=10)

    if "sub" in to_encode and isinstance(to_encode["sub"], UUID):
        to_encode["sub"] = str(to_encode["sub"])

    to_encode.update({"exp" : expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], session: Session = Depends(get_session)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate" : "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        usr_id = payload.get("sub")
        usr_role = payload.get("role_id")
        if usr_id is None or usr_role is None:
            raise credentials_exception
        token_data = TokenData(id=usr_id, role_id=usr_role)

    except (InvalidTokenError, ValueError):
        raise credentials_exception
    
    user = session.get(User, token_data.id)

    if user is None:
        raise credentials_exception
    
    return user

async def get_current_active_user(current_user: Annotated[User, Depends(get_current_user)],):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive User")
    
    return current_user