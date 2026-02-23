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

class LoginRequest(SQLModel):
    email: str
    password: str

class UserPublic(UserBase):
    id: UUID
    created_at: datetime
    
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