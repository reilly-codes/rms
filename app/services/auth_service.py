# app/services/auth_service.py
from uuid import UUID
from sqlmodel import Session, select
from fastapi import Request, Depends, HTTPException, status
from typing import Annotated

from app.core.database import get_session  # Clean import from core
from app.core.security import decode_token, verify_password, get_password_hash, create_access_token
from app.core.config import settings
from app.models.user import User
from app.schemas.token import TokenData
from app.schemas.user import PasswordChange, ResetPassword

class AuthService:
    @staticmethod
    def authenticate_user(session: Session, email: str, plain_txt_password: str) -> User | None:
        statement = select(User).where(User.email == email)
        user = session.exec(statement).first()

        if not user or not verify_password(plain_txt_password, user.hashed_password):
            return None
        return user

    @staticmethod
    def change_password(session: Session, current_user: User, password_data: PasswordChange):
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

    @staticmethod
    def reset_user_password(session: Session, reset_data: ResetPassword):
        try:
            payload = jwt.decode(reset_data.secret_token, settings.JWT_SECRET_KEY, algorithms=[settings.ALGORITHM])
            email: str = payload.get("sub")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token has expired")
        except jwt.PyJWTError:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid Token")
        
        if not email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User could not be found")
        
        if reset_data.new_password != reset_data.confirm_password:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="New Password and confirm password must match")
        
        qry = select(User).where(User.email == email)
        user = session.exec(qry).first()
        
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User could not be found")
        
        user.hashed_password = get_password_hash(reset_data.new_password)
        session.add(user)
        session.commit()
        session.refresh(user)
        return {"message": "Password reset successfully", "success": True, "status_code": status.HTTP_200_OK}

# REUSABLE FASTAPI DEPENDENCIES
async def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    token = request.cookies.get(settings.ACCESS_COOKIE_NAME)
    if not token:
        raise credentials_exception

    payload = decode_token(token, "access")
    usr_id = payload.get("sub")
    usr_role = payload.get("role_id")
    if usr_id is None or usr_role is None:
        raise credentials_exception
        
    token_data = TokenData(id=usr_id, role_id=usr_role)
    user = session.get(User, token_data.id)

    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if getattr(current_user, "disabled", False):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive User")
    return current_user

def issue_access_token_from_refresh(request: Request, session: Session) -> tuple[str, User]:
    refresh_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token provided")

    payload = decode_token(refresh_token, "refresh")
    usr_id = payload.get("sub")
    if usr_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = session.get(User, UUID(usr_id))
    if user is None or getattr(user, "disabled", False):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer valid")

    new_access_token = create_access_token(data={"sub": user.id, "role_id": user.role_id})
    return new_access_token, user