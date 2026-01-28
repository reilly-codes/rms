from enum import Enum
from sqlmodel import SQLModel, Field, Relationship
from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional, List

# enums
class HouseStatus(str, Enum):
    VACANT = "VACANT"
    OCCUPIED = "OCCUPIED"
    MAINTENANCE = "MAINTENANCE"

class TenantStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MOVING_OUT = "MOVING OUT"
    VACATED = "VACATED"

class InvoiceStatus(str, Enum):
    PAID = "PAID"
    UNPAID = "UNPAID"

class PaymentStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIIED = "VERIFIED"

# models

# Tokens
class Token(SQLModel):
    access_token: str
    token_type: str

class TokenData(SQLModel):
    id: UUID | None = None
    role_id: int | None = None

# Roles
class Role(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    description: str

# Users
class UserBase(SQLModel):
    name: str 
    email: str = Field(unique=True, index=True)
    tel: str
    role_id: int = Field(foreign_key="role.id", default=2)

class User(UserBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    hashed_password: str
    disabled: bool = False
    created_at: datetime = Field(default_factory=datetime.now)

    properties: List["Property"] = Relationship(back_populates="landlord")

class UserCreate(UserBase):
    password: str

class LoginRequest(SQLModel):
    email: str
    password: str

class UserPublic(UserBase):
    id: UUID
    created_at: datetime

# Properties
class PropertyBase(SQLModel):
    name: str
    address: str
    
class Property(PropertyBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    landlord_id: UUID = Field(foreign_key="user.id")

    landlord: "User" = Relationship(back_populates="properties")
    houses: List["House"] = Relationship(back_populates="property")

# Units
class HouseBase(SQLModel):
    number: str = Field(unique=True, index=True)
    rent: float
    deposit: float
    description: str
    status: HouseStatus = Field(default=HouseStatus.VACANT, index=True)

class House(HouseBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    property_id: UUID = Field(foreign_key="property.id")

    property: Property = Relationship(back_populates="houses")
    tenants: List["Tenant"] = Relationship(back_populates="house")


# Tenants
class TenantBase(UserBase):
    national_id: str = Field(unique=True, index=True)
    hse: UUID = Field(foreign_key="house.id")
    status: TenantStatus = Field(default=TenantStatus.ACTIVE, index=True)

class Tenant(TenantBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)

    house: "House" = Relationship(back_populates="tenants")

# Financials
# Invoices
class InvoiceBase(SQLModel):
    tenant_id: str = Field(foreign_key="tenant.id", index=True)
    hse_id: str = Field(foreign_key="house.id", index=True)
    amount: float
    status: InvoiceStatus = Field(default=InvoiceStatus.UNPAID, index=True)
    date_of_gen: datetime = Field(default_factory=datetime.now)
    date_due: datetime

class Invoice(InvoiceBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    comments: str | None
    created_at: datetime

    payments: List["Payment"] = Relationship(back_populates="invoice")

#transactions
class TransactionBase(SQLModel):
    transaction_id: str = Field(unique=True)
    transaction_date: datetime 
    amount: float

class Transaction(TransactionBase, table=True):
    id: UUID | None = Field(primary_key=True, default_factory=uuid4)
    

# Payments
class PaymentBase(SQLModel):
    invoice_id: str = Field(foreign_key="invoice.id", index=True)
    amount_expected: float
    amount_paid: float
    transcation_id: str = Field(foreign_key="transaction.id", index=True)
    status: PaymentStatus = Field(default=PaymentStatus.UNVERIFIED, index=True)

class Payment(PaymentBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)

    invoice: Invoice = Relationship(back_populates="payments")
