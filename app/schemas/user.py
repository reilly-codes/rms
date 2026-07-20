from sqlmodel import SQLModel, Field
from uuid import UUID
from datetime import datetime

class UserBase(SQLModel):
    name: str 
    email: str = Field(unique=True, index=True)
    tel: str
    role_id: int = Field(foreign_key="role.id", default=2)
    
class UserCreate(UserBase):
    password: str

class CaretakerCreate(SQLModel):
    name: str
    email: str
    tel: str
    password: str

class CaretakerUpdate(SQLModel):
    name: str | None = None
    email: str | None = None
    tel: str | None = None
    password: str | None = None

class PropertyManagerCreate(SQLModel):
    name: str
    email: str
    tel: str
    password: str

class PropertyManagerUpdate(SQLModel):
    name: str | None = None
    email: str | None = None
    tel: str | None = None
    password: str | None = None

class LoginRequest(SQLModel):
    email: str
    password: str

class UserPublic(UserBase):
    id: UUID
    created_at: datetime
    landlord_id: UUID | None = None
    
class PasswordChange(SQLModel):
    current_password: str
    new_password: str
    confirm_password: str
    
    # reset password comes with tenants module
class RequestResetPassword(SQLModel):
    email: str    

class ResetPassword(SQLModel):
    secret_token: str
    new_password: str
    confirm_password: str