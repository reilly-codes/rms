from fastapi import APIRouter, Depends, HTTPException
from typing import Annotated, List
from datetime import timedelta, datetime
from sqlmodel import select
from sqlalchemy.orm import selectinload
from uuid import UUID

from app.models.user import User
from app.auth import get_current_active_user, get_password_hash, change_password
from app.schemas.user import UserPublic, UserCreate, PasswordChange
from app.db import SessionDep

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)

@router.get("/current", response_model=User)
async def active_user(
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    return current_user

@router.post("/create", response_model=UserPublic)
async def register_landlord(
    user_input: UserCreate, session: SessionDep
):
    user_data = user_input.model_dump()
    plain_password = user_data.pop("password")
    user_data["hashed_password"] = get_password_hash(plain_password)
    user = User(**user_data)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

@router.post("/change-password")
async def change_user_password(
    password_data: PasswordChange,
    current_user: Annotated[User, Depends(active_user)],
    session: SessionDep
):
    return await change_password(password_data, current_user, session)