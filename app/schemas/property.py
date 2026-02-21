from sqlmodel import SQLModel

class PropertyBase(SQLModel):
    name: str
    address: str