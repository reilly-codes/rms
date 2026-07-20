# app/routers/users.py
import os
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status, Header, Response
from typing import Annotated, Optional
from uuid import UUID
from sqlmodel import select
from fastapi_mail import FastMail, MessageSchema, MessageType, ConnectionConfig
from starlette.background import BackgroundTasks
from sqlalchemy.exc import IntegrityError

# Core database and configurations
from app.core.database import SessionDep
from app.core.config import settings
from app.core.roles import require_landlord
from app.core.security import (
    get_password_hash, 
    clear_auth_cookies, 
    settings as security_settings
)

# Models and schemas
from app.models.user import User
from app.schemas.user import (
    UserPublic, 
    UserCreate, 
    CaretakerCreate, 
    CaretakerUpdate, 
    PropertyManagerCreate,
    PropertyManagerUpdate,
    PasswordChange, 
    RequestResetPassword, 
    ResetPassword
)

# Services
from app.services.auth_service import (
    AuthService, 
    get_current_active_user, 
    get_current_active_user as active_user  # Alias to keep API routes fully backward compatible
)
from app.services.cascade_delete import delete_landlord_cascade

# Load secure token configuration helper logic
import jwt

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
async def get_active_user(
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    return current_user

@router.post("/create", response_model=UserPublic)
async def register_landlord(
    user_input: UserCreate, 
    session: SessionDep
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

    from app.services.subscription_service import SubscriptionService
    SubscriptionService.create_account_with_trial(session, user)

    return user

@router.post("/caretakers/create", response_model=UserPublic)
async def create_caretaker(
    caretaker_input: CaretakerCreate,
    current_landlord: Annotated[User, Depends(require_landlord)],
    session: SessionDep,
):
    caretaker = User(
        name=caretaker_input.name,
        email=caretaker_input.email,
        tel=caretaker_input.tel,
        # BUGFIX: this was hardcoded to 3 (Tenant) even though ROLE_MAP swapped
        # Caretaker to id=2 a while back. Every "caretaker" created since then
        # was silently logging in with Tenant-level access. Confirm existing
        # rows in prod: `select id, email, role_id from "user" where landlord_id
        # is not null and role_id = 3` — anything in there that's actually a
        # caretaker needs a one-off UPDATE to role_id = 2.
        role_id=2,
        landlord_id=current_landlord.id,
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
    current_landlord: Annotated[User, Depends(require_landlord)],
    session: SessionDep,
):
    statement = select(User).where(User.landlord_id == current_landlord.id).where(User.role_id == 2)
    return session.exec(statement).all()

async def get_owned_caretaker(
    caretaker_id: UUID,
    current_landlord: Annotated[User, Depends(require_landlord)],
    session: SessionDep,
) -> User:
    """Shared scoping check: only the landlord who created a caretaker can view/edit/delete them."""
    caretaker = session.exec(
        select(User)
        .where(User.id == caretaker_id)
        .where(User.landlord_id == current_landlord.id)
        .where(User.role_id == 2)
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

# --- Property Managers ---------------------------------------------------
# A Property Manager is its own role (role_id=4). Unlike Caretakers, a
# Property Manager can end up with access to properties belonging to
# *other* landlords too — that access is granted separately through
# PropertyAssignment (see app/routers/property_assignments.py), not through
# this creation endpoint. This endpoint only creates the native login
# account, scoped to the landlord who created it (same as Caretakers).
# Only accounts on a Property Management plan may create these — see
# app/services/subscription_service.py::require_property_management_plan.

@router.post("/property-managers/create", response_model=UserPublic)
async def create_property_manager(
    pm_input: PropertyManagerCreate,
    current_landlord: Annotated[User, Depends(require_landlord)],
    session: SessionDep,
):
    from app.services.subscription_service import SubscriptionService

    SubscriptionService.require_property_management_plan(session, current_landlord)

    pm = User(
        name=pm_input.name,
        email=pm_input.email,
        tel=pm_input.tel,
        role_id=4,
        landlord_id=current_landlord.id,
        hashed_password=get_password_hash(pm_input.password),
    )
    session.add(pm)
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        if "email" in str(e.orig):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An account with this email already exists")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not create property manager — invalid reference data")
    session.refresh(pm)
    return pm

@router.get("/property-managers", response_model=list[UserPublic])
async def list_property_managers(
    current_landlord: Annotated[User, Depends(require_landlord)],
    session: SessionDep,
):
    statement = select(User).where(User.landlord_id == current_landlord.id).where(User.role_id == 4)
    return session.exec(statement).all()

async def get_owned_property_manager(
    pm_id: UUID,
    current_landlord: Annotated[User, Depends(require_landlord)],
    session: SessionDep,
) -> User:
    pm = session.exec(
        select(User)
        .where(User.id == pm_id)
        .where(User.landlord_id == current_landlord.id)
        .where(User.role_id == 4)
    ).first()

    if not pm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property manager not found")

    return pm

@router.patch("/property-managers/{pm_id}", response_model=UserPublic)
async def edit_property_manager(
    pm_update: PropertyManagerUpdate,
    pm: Annotated[User, Depends(get_owned_property_manager)],
    session: SessionDep,
):
    update_data = pm_update.model_dump(exclude_unset=True)
    plain_password = update_data.pop("password", None)

    for key, value in update_data.items():
        setattr(pm, key, value)

    if plain_password:
        pm.hashed_password = get_password_hash(plain_password)

    session.add(pm)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An account with this email already exists")
    session.refresh(pm)
    return pm

@router.delete("/property-managers/{pm_id}")
async def delete_property_manager(
    pm: Annotated[User, Depends(get_owned_property_manager)],
    session: SessionDep,
):
    from app.services.property_assignment_service import PropertyAssignmentService

    # Revoke every assignment (from any landlord) before deleting the login itself.
    PropertyAssignmentService.revoke_all_for_user(session, pm.id)
    session.delete(pm)
    session.commit()
    return {"message": "Property manager removed successfully"}

@router.delete("/me")
async def delete_my_account(
    current_user: Annotated[User, Depends(active_user)],
    session: SessionDep,
    response: Response,
):
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
    # Delegate cleanly to AuthService implementation
    return AuthService.change_password(session, current_user, password_data)

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
    
    origin_strings = os.getenv("ALLOWED_FRONTENDS", "https://rms.oduorys.co.ke")
    ALLOWED_ORIGINS_LIST = [url.strip() for url in origin_strings.split(",") if url.strip()]
    
    try:
        # Create security password reset token payload
        token_payload = {
            "sub": user.email,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10)
        }
        reset_token = jwt.encode(token_payload, security_settings.JWT_SECRET_KEY, algorithm=security_settings.ALGORITHM)
        
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
        
        return { 
            "message": f"Reset password email has been sent to {user.email}", 
            "success": True, 
            "status_code": status.HTTP_200_OK 
        }
        
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Could not complete request")
    
@router.post("/reset-password/")
async def reset_user_password(
    session: SessionDep,
    reset_data: ResetPassword
):
    # Delegate cleanly to AuthService implementation
    return AuthService.reset_user_password(session, reset_data)