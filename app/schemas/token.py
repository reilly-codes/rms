from sqlmodel import SQLModel
from uuid import UUID

class Token(SQLModel):
    access_token: str
    token_type: str

class TokenData(SQLModel):
    id: UUID | None = None
    role_id: int | None = None