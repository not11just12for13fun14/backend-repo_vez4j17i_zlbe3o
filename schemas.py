"""
DriveShare Capital - Database Schemas

Each Pydantic model below maps to a MongoDB collection with the lowercase
class name as the collection name. For example: User -> "user".

10 shares = 1 car. Offerings define car pools (SPVs) with a number of cars,
term, pricing, and status. Investments track user pledges and instalments.
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Literal
from datetime import datetime


class User(BaseModel):
    name: str
    email: EmailStr
    role: Literal["investor", "admin"] = "investor"
    is_active: bool = True


class KYC(BaseModel):
    user_id: str
    status: Literal["pending", "approved", "rejected"] = "pending"
    document_type: Literal["passport", "driver_license", "id_card"]
    document_number: str
    country: str
    submitted_at: Optional[datetime] = None


class SPV(BaseModel):
    name: str
    description: Optional[str] = None
    manager: Optional[str] = None
    status: Literal["active", "closed"] = "active"


class Vehicle(BaseModel):
    spv_id: Optional[str] = None
    vin: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    photo_url: Optional[str] = None
    status: Literal["available", "rented", "maintenance"] = "available"


class Offering(BaseModel):
    title: str
    spv_id: Optional[str] = None
    description: Optional[str] = None
    cars_count: int = Field(..., ge=1)
    shares_total: int = Field(..., ge=10, description="Total shares; must be cars_count * 10")
    share_price: float = Field(..., ge=0)
    term_months: int = Field(..., ge=1)
    status: Literal["open", "closed", "fully_subscribed"] = "open"
    images: Optional[List[str]] = None


class Investment(BaseModel):
    user_id: str
    offering_id: str
    shares: int = Field(..., ge=1)
    pledge_amount: float = Field(..., ge=0)
    monthly_instalment: float = Field(..., ge=0)
    months: int = Field(..., ge=1)
    status: Literal["active", "exited", "defaulted"] = "active"


class Instalment(BaseModel):
    user_id: str
    investment_id: str
    amount: float
    due_month: int
    paid: bool = False


class Wallet(BaseModel):
    user_id: str
    balance: float = 0.0
    currency: str = "USD"


class Transaction(BaseModel):
    user_id: str
    type: Literal[
        "topup",
        "instalment_payment",
        "rental_distribution",
        "exit_payout",
        "trade_settlement",
    ]
    amount: float
    reference_id: Optional[str] = None
    meta: Optional[dict] = None


class Distribution(BaseModel):
    offering_id: str
    month: int
    total_amount: float
    per_share: float


class Notification(BaseModel):
    user_id: str
    title: str
    message: str
    read: bool = False


class Document(BaseModel):
    user_id: str
    name: str
    url: Optional[str] = None
    status: Literal["pending", "signed"] = "pending"


class SecondaryOrder(BaseModel):
    user_id: str
    offering_id: str
    side: Literal["buy", "sell"]
    shares: int
    price_per_share: float
    status: Literal["open", "matched", "cancelled"] = "open"
