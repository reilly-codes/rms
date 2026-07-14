import os
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status, Header, Response
from typing import Annotated, Optional
from uuid import UUID
from sqlmodel import select
from fastapi_mail import FastMail, MessageSchema, MessageType, ConnectionConfig
from starlette.background import BackgroundTasks

from app.models.user import User
from app.auth import get_current_active_user, get_password_hash, change_password, create_reset_password_token, reset_password, clear_auth_cookies
from app.schemas.user import UserPublic, UserCreate, CaretakerCreate, CaretakerUpdate, PasswordChange, RequestResetPassword, ResetPassword
from app.db import SessionDep
from app.services.cascade_delete import delete_landlord_cascade
from sqlalchemy.exc import IntegrityError

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)

load_dotenv()

mail_conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_FROM"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER=os.getenv("MAIL_SERVER"),
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
    SUPPRESS_SEND=1
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
    # role_id is intentionally forced here, not trusted from the client —
    # this endpoint is public self-registration, and it must only ever be
    # able to create Landlords. Caretakers/Tenants are created by an
    # existing Landlord via their own dedicated, authenticated endpoints.
    user_data["role_id"] = 1
    user_data["landlord_id"] = None
    user_data["hashed_password"] = get_password_hash(plain_password)
    user = User(**user_data)
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An account with this email already exists")
    session.refresh(user)
    return user

@router.post("/caretakers/create", response_model=UserPublic)
async def create_caretaker(
    caretaker_input: CaretakerCreate,
    current_user: Annotated[User, Depends(active_user)],
    session: SessionDep,
):
    if current_user.role_id != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only landlords can add caretakers")

    caretaker = User(
        name=caretaker_input.name,
        email=caretaker_input.email,
        tel=caretaker_input.tel,
        role_id=3,
        landlord_id=current_user.id,
        hashed_password=get_password_hash(caretaker_input.password),
    )
    session.add(caretaker)
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        if "email" in str(e.orig):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An account with this email already exists")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not create caretaker — invalid reference data")
    session.refresh(caretaker)
    return caretaker

@router.get("/caretakers", response_model=list[UserPublic])
async def list_caretakers(
    current_user: Annotated[User, Depends(active_user)],
    session: SessionDep,
):
    if current_user.role_id != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only landlords can view their caretakers")

    statement = select(User).where(User.landlord_id == current_user.id).where(User.role_id == 3)
    return session.exec(statement).all()

async def get_owned_caretaker(
    caretaker_id: UUID,
    current_user: Annotated[User, Depends(active_user)],
    session: SessionDep,
) -> User:
    """Shared scoping check: only the landlord who created a caretaker can view/edit/delete them."""
    if current_user.role_id != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only landlords can manage caretakers")

    caretaker = session.exec(
        select(User)
        .where(User.id == caretaker_id)
        .where(User.landlord_id == current_user.id)
        .where(User.role_id == 3)
    ).first()

    if not caretaker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caretaker not found")

    return caretaker

@router.patch("/caretakers/{caretaker_id}", response_model=UserPublic)
async def edit_caretaker(
    caretaker_update: CaretakerUpdate,
    caretaker: Annotated[User, Depends(get_owned_caretaker)],
    session: SessionDep,
):
    update_data = caretaker_update.model_dump(exclude_unset=True)
    plain_password = update_data.pop("password", None)

    for key, value in update_data.items():
        setattr(caretaker, key, value)

    if plain_password:
        caretaker.hashed_password = get_password_hash(plain_password)

    session.add(caretaker)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An account with this email already exists")
    session.refresh(caretaker)
    return caretaker

@router.delete("/caretakers/{caretaker_id}")
async def delete_caretaker(
    caretaker: Annotated[User, Depends(get_owned_caretaker)],
    session: SessionDep,
):
    session.delete(caretaker)
    session.commit()
    return {"message": "Caretaker removed successfully"}

@router.delete("/me")
async def delete_my_account(
    current_user: Annotated[User, Depends(active_user)],
    session: SessionDep,
    response: Response,
):
    """Self-service account deletion.

    - Landlord: full cascade delete — every property, house, tenant (and
      their logins), invoice, payment, and caretaker they own goes with them.
      This is the mechanism for "suspended for non-payment -> deleted" too,
      once subscription tracking exists to decide *when* to call this.
    - Caretaker: just removes their own account.
    - Tenant: blocked here — tenant deletion must be landlord-initiated via
      DELETE /tenants/{tenant_id}, since a tenant deleting themselves would
      orphan lease/payment history their landlord still needs.
    """
    if current_user.role_id == 1:
        delete_landlord_cascade(session, current_user)
    elif current_user.role_id == 3:
        session.delete(current_user)
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant accounts can't self-delete — ask your landlord to remove you.",
        )

    session.commit()
    clear_auth_cookies(response)
    return {"message": "Account and all associated records deleted successfully"}

@router.patch("/change-password")
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
    if not user_email.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot have empty email")
    qry = select(User).where(User.email == user_email.email)
    
    user = session.exec(qry).first()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User could not be found")
    
    # send email logic
    origin_strings = os.getenv("ALLOWED_FRONTENDS", "http://localhost:8080/,https://rms.oduorys.co.ke")
    ALLOWED_ORIGINS_LIST = origin_strings.split(",")
    try:
        reset_token = create_reset_password_token(user)
        print("Token : ",reset_token)
        if origin and origin in ALLOWED_ORIGINS_LIST:
            frontend_url = origin
        else:
            frontend_url = ALLOWED_ORIGINS_LIST[0]
        forgot_url = f"{frontend_url}/reset-password?token={reset_token}"
        plain_text_body = f"Click the link to reset your password: {forgot_url}\n\nThis link expires in 10 minutes."
        
        message = MessageSchema(
            subject="Password Reset Instructions",
            recipients=[user.email],
            body=plain_text_body, 
            subtype=MessageType.plain
        )
        
        fm = FastMail(mail_conf)
        bg_tasks.add_task(fm.send_message, message)
        
        print(message)
        
        return { "message" : f"Reset password email has been sent to {user.email}", "success" : True, "status_code" : status.HTTP_200_OK }
        
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Could not complete request")
    
@router.post("/reset-password/")
async def reset_user_password(
    session: SessionDep,
    reset_data: ResetPassword
):
    
    return await reset_password(reset_data, session)