import uuid
import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Text, Numeric, Integer
)
from sqlalchemy.orm import relationship
from .database import Base


def new_id():
    return str(uuid.uuid4())


def now():
    return datetime.datetime.utcnow()


# ---- Users -----------------------------------------------------------
# Every identity in Shelter — from an anonymous browser who just verified
# a phone number, up to a fully-verified Agent — is one User row. `role`
# and `kyc_status` together decide what they're allowed to do, matching
# the progressive identity model in the spec: browsing is anonymous,
# messaging/booking needs a light identity, sharing a room needs a mini
# profile, and listing Rent/Short-let needs a verified Landlord/Agent
# account. No separate "guest" table — the identity is permanent once
# created, so escrow and disputes always have an owner.
class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=new_id)
    phone = Column(String, unique=True, nullable=True, index=True)
    email = Column(String, unique=True, nullable=True, index=True)
    name = Column(String, nullable=True)  # required once they message/list; optional at pure-browse stage
    role = Column(String, nullable=False, default="light")  # light | everyday | landlord | agent | admin
    profile_photo_url = Column(String, nullable=True)
    bio = Column(Text, nullable=True)  # roommate mini-profile short bio

    # Landlord/Agent professional fields
    password_hash = Column(String, nullable=True)  # only Landlord/Agent accounts use a password — everyday/light identities stay OTP-only
    state = Column(String, nullable=True)
    lga = Column(String, nullable=True)
    business_name = Column(String, nullable=True)  # Agent accounts only
    payout_nuban = Column(String, nullable=True)
    lasrera_id = Column(String, nullable=True)  # Lagos agents only, optional

    kyc_status = Column(String, nullable=False, default="none")  # none | pending | approved | rejected

    is_phone_verified = Column(Boolean, default=False)
    is_email_verified = Column(Boolean, default=False)

    created_at = Column(DateTime, default=now)

    kyc_documents = relationship("KycDocument", back_populates="user", cascade="all, delete-orphan", foreign_keys="KycDocument.user_id")
    listings = relationship("Listing", back_populates="owner", cascade="all, delete-orphan")


# ---- One-time codes ----------------------------------------------------
# DUMMY OTP for now: request_otp always issues a fixed test code and
# returns it directly in the API response instead of sending a real SMS,
# so the whole auth flow is testable without an SMS provider. Swappable
# for a real provider later without touching anything downstream of
# verify_otp.
class OtpCode(Base):
    __tablename__ = "otp_codes"

    id = Column(String, primary_key=True, default=new_id)
    identifier = Column(String, nullable=False, index=True)  # phone or email
    code = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    consumed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)


# ---- Listings ------------------------------------------------------
# One table for all 3 verticals (type = rent | shortlet | roommate),
# since they share most fields; type-specific fields are simply nullableingredients
# on the same row rather than 3 separate tables, to keep search/filter simple.
class Listing(Base):
    __tablename__ = "listings"

    id = Column(String, primary_key=True, default=new_id)
    type = Column(String, nullable=False)  # rent | shortlet | roommate
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    state = Column(String, nullable=False)
    lga = Column(String, nullable=False)

    beds = Column(Integer, nullable=True)
    baths = Column(Integer, nullable=True)
    amenities = Column(Text, nullable=True)  # comma-separated for simplicity across DB engines

    # Rent-specific pricing (itemised, per spec)
    annual_rent = Column(Numeric, nullable=True)
    caution_fee = Column(Numeric, nullable=True)
    service_charge = Column(Numeric, nullable=True)
    agency_fee = Column(Numeric, nullable=True)

    # Short-let specific
    nightly_rate = Column(Numeric, nullable=True)

    # Roommate specific
    total_rent = Column(Numeric, nullable=True)       # total rent for the whole place
    roommate_share = Column(Numeric, nullable=True)   # what the new roommate pays
    gender_preference = Column(String, nullable=True)  # male | female | any
    house_rules = Column(Text, nullable=True)
    available_from = Column(DateTime, nullable=True)

    status = Column(String, nullable=False, default="pending_review")  # pending_review | live | suspended | occupied
    created_at = Column(DateTime, default=now)

    owner = relationship("User", back_populates="listings")
    photos = relationship("ListingPhoto", back_populates="listing", cascade="all, delete-orphan", order_by="ListingPhoto.position")


class ListingPhoto(Base):
    __tablename__ = "listing_photos"

    id = Column(String, primary_key=True, default=new_id)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=False)
    url = Column(String, nullable=False)
    position = Column(Integer, default=0)

    listing = relationship("Listing", back_populates="photos")


# ---- Messaging -----------------------------------------------------
# On-site inbox only, per spec — no WhatsApp deal channel. Phone numbers
# are never exposed through this table; the frontend never renders raw
# phone digits from a User row on a listing's public side.
class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=new_id)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=False)
    sender_id = Column(String, ForeignKey("users.id"), nullable=False)
    recipient_id = Column(String, ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now)
    read_at = Column(DateTime, nullable=True)


class MeetingRequest(Base):
    __tablename__ = "meeting_requests"

    id = Column(String, primary_key=True, default=new_id)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=False)
    requester_id = Column(String, ForeignKey("users.id"), nullable=False)
    proposed_time = Column(DateTime, nullable=True)
    status = Column(String, nullable=False, default="pending")  # pending | accepted | declined
    created_at = Column(DateTime, default=now)


class PictureRequest(Base):
    __tablename__ = "picture_requests"

    id = Column(String, primary_key=True, default=new_id)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=False)
    requester_id = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending | fulfilled
    created_at = Column(DateTime, default=now)


# ---- Escrow / payments ----------------------------------------------
# DUMMY for now: "Pay with protection" instantly writes a HELD row —
# no real Paystack/Flutterwave call. Released either by the renter
# confirming move-in, or (for short-let) automatically once the
# check-in window closes without a dispute. Swapping in a real gateway
# later only changes how a Transaction gets created and released, not
# this table's shape.
class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True, default=new_id)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=False)
    renter_id = Column(String, ForeignKey("users.id"), nullable=False)
    amount = Column(Numeric, nullable=False)
    breakdown = Column(Text, nullable=True)  # simple JSON-as-text line-item breakdown
    payment_method = Column(String, nullable=True)  # card | bank_transfer (both dummy for now)
    status = Column(String, nullable=False, default="held")  # held | released | refunded | failed
    created_at = Column(DateTime, default=now)
    released_at = Column(DateTime, nullable=True)


# ---- KYC documents ----------------------------------------------------
# DUMMY for now: documents just get stored and reviewed manually by an
# admin (approve/reject) — no automated vendor call. A Landlord/Agent's
# listings only go live once kyc_status on their User row is "approved".
class KycDocument(Base):
    __tablename__ = "kyc_documents"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    doc_type = Column(String, nullable=False)  # government_id | agency_license_or_cofo
    file_url = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending | approved | rejected
    uploaded_at = Column(DateTime, default=now)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True)

    user = relationship("User", back_populates="kyc_documents", foreign_keys=[user_id])
