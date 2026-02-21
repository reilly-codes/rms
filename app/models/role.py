from sqlmodel import SQLModel, Field

class Role(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str | None = Field(unique=True, default=None)
    description: str | None = None