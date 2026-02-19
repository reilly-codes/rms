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
    
class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    MATCHED = "MATCHED"
    IGNORED = "IGNORED"

class PaymentStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIIED = "VERIFIED"

class BillType(str, Enum):
    WATER = "WATER"
    ELECTRICITY = "ELECTRICITY"
    OTHER = "OTHER"
    
class MaintenanceStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN PROGRESS"
    COMPLETED = "COMPLETED"
    
class MaintenancePaymentStatus(str, Enum):
    PAID = "PAID"
    UNPAID = "UNPAID"
    
class MessageType(str, Enum):
    WHATSAPP = "WHATSAPP"
    SMS = "SMS"
    
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
    name: str | None = Field(unique=True, default=None)
    description: str | None = None

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
    
class PasswordChange(SQLModel):
    current_password: str
    new_password: str
    confirm_password: str
    
    # reset password comes with tenants module
    
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
    wallet_balance: float = Field(default=0.0)

    house: "House" = Relationship(back_populates="tenants")

# Financials
# Invoices
class InvoiceBase(SQLModel):
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    hse_id: UUID = Field(foreign_key="house.id", index=True)
    rent_amount: float | None
    amount: float | None
    status: InvoiceStatus = Field(default=InvoiceStatus.UNPAID, index=True)
    date_of_gen: datetime = Field(default_factory=datetime.now)
    date_due: datetime

class Invoice(InvoiceBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    comments: str | None

    payments: List["Payment"] = Relationship(back_populates="invoice")
    utilities: List["UtilityBill"] = Relationship(back_populates="invoice")
    house: "House" = Relationship()
    tenant: "Tenant" = Relationship()

class InvoiceGenerationRequest(SQLModel):
    utilities: List[UtilityBillBase]
    
class InvoiceRead(InvoiceBase):
    id: UUID
    comments: str | None
    
    house: House | None = None
    tenant: Tenant | None = None
    utilities: List[UtilityBill] = []
#transactions
class TransactionBase(SQLModel):
    transaction_reference: str = Field(unique=True)
    transaction_date: datetime 
    amount: float 
    transaction_status: TransactionStatus = Field(default=TransactionStatus.PENDING)
    

class Transaction(TransactionBase, table=True):
    id: UUID | None = Field(primary_key=True, default_factory=uuid4)
    
    payments: List["Payment"] = Relationship(back_populates="transaction")
    

# Payments
class PaymentBase(SQLModel):
    invoice_id: UUID | None = Field(foreign_key="invoice.id", index=True, default=None)
    maintenance_bill_id: UUID | None = Field(foreign_key="maintenancebill.id", index=True)
    amount_expected: float | None = None
    amount_paid: float
    transaction_ref: str = Field(index=True)
    status: PaymentStatus = Field(default=PaymentStatus.UNVERIFIED, index=True)
    created_by: UUID| None = Field(foreign_key="user.id", default=None)

class Payment(PaymentBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    transaction_id: UUID | None = Field(foreign_key="transaction.id", index=True)
    created_at: datetime = Field(default_factory=datetime.now)

    invoice: Optional["Invoice"] = Relationship(back_populates="payments")
    maintenance_bill: Optional["MaintenanceBill"] = Relationship(back_populates="payments")
    transaction: Transaction = Relationship(back_populates="payments")


# Utilities
class UtilityBillBase(SQLModel):
    date_gen: datetime = Field(default_factory=datetime.now)
    bill_type: BillType
    amount : float

class UtilityBill(UtilityBillBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    invoice_id: UUID = Field(foreign_key="invoice.id", index=True)

    invoice: Invoice = Relationship(back_populates="utilities")


# Maintenance
class MaintenanceBillBase(SQLModel):
    hse_id: UUID = Field(foreign_key="house.id", index=True)
    tenant_id: UUID | None = Field(foreign_key="tenant.id", default=None, index=True)
    title: str
    description: str | None
    labor_cost: float | None = None
    parts_cost: float | None = None
    total_amount: float | None = None
    
    status: MaintenanceStatus = Field(default=MaintenanceStatus.PENDING)
    payment_status: MaintenancePaymentStatus = Field(default=MaintenancePaymentStatus.UNPAID)
    
    date_raised: datetime | None = Field(default_factory=datetime.now)
    
class MaintenanceBillUpdate(SQLModel):
    labor_cost: float | None = None
    parts_cost: float | None = None
    
class MaintenanceBill(MaintenanceBillBase, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    
    house: "House" = Relationship()
    tenant: "Tenant" = Relationship()
    
    payments: List["Payment"] = Relationship(back_populates="maintenance_bill")
    
class MaintenanceBillRead(MaintenanceBillBase):
    id: UUID
    
    house: House | None = None
    tenant: Tenant | None = None
    
class EditMaintenanceStatus(SQLModel):
    status: MaintenanceStatus | None = None
    
class BroadcastBase(SQLModel):
    message: str
    message_type: MessageType = Field(default=MessageType.WHATSAPP)
    recepient: List[UUID]
    
class Broadcast(BroadcastBase):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    sent_at: datetime | None = Field(default_factory=datetime.now)
    