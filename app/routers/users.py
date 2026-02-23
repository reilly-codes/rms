import os
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status, Header
from typing import Annotated, Optional
from sqlmodel import select
from fastapi_mail import FastMail, MessageSchema, MessageType, ConnectionConfig
from starlette.background import BackgroundTasks

from app.models.user import User
from app.auth import get_current_active_user, get_password_hash, change_password, create_reset_password_token, reset_password
from app.schemas.user import UserPublic, UserCreate, PasswordChange, RequestResetPassword, ResetPassword
from app.db import SessionDep

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)

mail_conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_FROM"),
    MAIL_PORT=os.getenv("MAIL_PORT"),
    MAIL_SERVER=os.getenv("MAIL_SERVER"),
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
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

@router.post("/forgot-password")
async def request_reset_password_link(
    session: SessionDep,
    user_email: RequestResetPassword,
    bg_tasks: BackgroundTasks,
    origin: Optional[str] = Header(default=None)
):
    if not user_email.model_validate_json:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot have empty email")
    qry = select(User).where(User.email == user_email.email)
    
    user = session.exec(qry).first()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User could not be found")
    
    # send email logic
    origin_strings = os.getenv("ALLOWED_FRONTENDS")
    ALLOWED_ORIGINS_LIST = origin_strings.split(",")
    try:
        reset_token = create_reset_password_token(user)
        if origin and origin in ALLOWED_ORIGINS_LIST:
            frontend_url = origin
        forgot_url = f"{frontend_url}/reset-password?token={reset_token}"
        email_body = {
            "link_expiry" : "10 Minutes",
            "reset_link" : forgot_url
        }
        message = MessageSchema(
            subject="Password Reset Instructions",
            recipients=[user.email],
            template_body=email_body,
            subtype=MessageType.html
        )
        
        template_name = None
        fm = FastMail(mail_conf)
        bg_tasks.add_task(fm.send_message, message, template_name)
        
        return { "message" : f"Reset password email has been sent to {user.email}", "success" : True, "status_code" : status.HTTP_200_OK }
        
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Could not complete request")
    
@router.post("/reset-password/")
async def reset_user_password(
    session: SessionDep,
    reset_data: ResetPassword
):
    
    return await reset_password(reset_data, session)