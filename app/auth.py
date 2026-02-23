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

from app.db import get_session
from app.models.user import User
from app.schemas.token import TokenData
from app.schemas.user import PasswordChange, ResetPassword


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
    token = jwt.encode(data, JWT_SECRET_KEY, algorithms=[ALGORITHM])
    
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
    
    hashed_password = get_password_hash(reset_data.new_password)
    user.hashed_password = hashed_password
    session.add(user)
    session.commit()
    session.refresh(user)
    
    return {"message" :  "Password reset successfully", "succes" : True, "status_code" : status.HTTP_200_OK}