from pydantic import BaseModel
from typing import Optional, List
import datetime


class RequestOtpBody(BaseModel):
    identifier: str  # phone or email


class VerifyOtpBody(BaseModel):
    identifier: str
    code: str
    name: Optional[str] = None  # allow setting name at verification time (light profile)


class UpdateProfileBody(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    profile_photo_url: Optional[str] = None


class BecomeListerBody(BaseModel):
    role: str  # landlord | agent
    name: str
    email: str
    profile_photo_url: str  # mandatory for landlord/agent
    lasrera_id: Optional[str] = None  # Lagos agents only, optional


class ListerRegisterBody(BaseModel):
    role: str  # landlord | agent
    name: str
    state: str
    lga: str
    business_name: Optional[str] = None  # Agent accounts only
    phone: str
    email: str
    password: str


class ListerLoginBody(BaseModel):
    email: str
    password: str


class ListingCreateBody(BaseModel):
    type: str  # rent | shortlet | roommate
    title: str
    description: Optional[str] = None
    state: str
    lga: str
    beds: Optional[int] = None
    baths: Optional[int] = None
    amenities: Optional[str] = None

    annual_rent: Optional[float] = None
    caution_fee: Optional[float] = None
    service_charge: Optional[float] = None
    agency_fee: Optional[float] = None

    nightly_rate: Optional[float] = None

    total_rent: Optional[float] = None
    roommate_share: Optional[float] = None
    gender_preference: Optional[str] = None
    house_rules: Optional[str] = None
    available_from: Optional[datetime.datetime] = None

    photo_urls: List[str] = []


class MessageCreateBody(BaseModel):
    listing_id: str
    recipient_id: str
    body: str


class TransactionCreateBody(BaseModel):
    listing_id: str
    payment_method: str  # card | bank_transfer
