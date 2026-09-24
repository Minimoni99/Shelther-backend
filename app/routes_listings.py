import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from . import models, schemas
from .database import get_db
from .auth import current_user, current_user_optional

router = APIRouter(prefix="/api/listings", tags=["listings"])

MIN_ROOMMATE_PHOTOS = 10


def _owner_summary(owner: models.User) -> dict:
    return {
        "id": owner.id,
        "name": owner.name,
        "role": owner.role,
        "profile_photo_url": owner.profile_photo_url,
        "verified": owner.kyc_status == "approved" if owner.role in ("landlord", "agent") else None,
    }


def _listing_out(l: models.Listing, db: Session) -> dict:
    return {
        "id": l.id,
        "type": l.type,
        "title": l.title,
        "description": l.description,
        "state": l.state,
        "lga": l.lga,
        "beds": l.beds,
        "baths": l.baths,
        "amenities": l.amenities,
        "annual_rent": float(l.annual_rent) if l.annual_rent else None,
        "caution_fee": float(l.caution_fee) if l.caution_fee else None,
        "service_charge": float(l.service_charge) if l.service_charge else None,
        "agency_fee": float(l.agency_fee) if l.agency_fee else None,
        "nightly_rate": float(l.nightly_rate) if l.nightly_rate else None,
        "total_rent": float(l.total_rent) if l.total_rent else None,
        "roommate_share": float(l.roommate_share) if l.roommate_share else None,
        "gender_preference": l.gender_preference,
        "house_rules": l.house_rules,
        "available_from": l.available_from.isoformat() if l.available_from else None,
        "status": l.status,
        "created_at": l.created_at.isoformat(),
        "photos": [p.url for p in l.photos],
        "owner": _owner_summary(l.owner),
    }


@router.post("")
def create_listing(body: schemas.ListingCreateBody, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if body.type not in ("rent", "shortlet", "roommate"):
        raise HTTPException(status_code=400, detail="type must be rent, shortlet, or roommate.")

    if body.type == "roommate":
        if user.role in ("landlord", "agent"):
            raise HTTPException(status_code=403, detail="Share Your Room is only available to everyday users, not Landlord/Agent accounts.")
        if not user.name:
            raise HTTPException(status_code=400, detail="Complete your mini profile (name) before sharing a room.")
        if len(body.photo_urls) < MIN_ROOMMATE_PHOTOS:
            raise HTTPException(status_code=400, detail=f"At least {MIN_ROOMMATE_PHOTOS} photos are required.")
        if body.gender_preference not in ("male", "female", "any"):
            raise HTTPException(status_code=400, detail="gender_preference must be male, female, or any.")
        if user.role == "light":
            user.role = "everyday"
    else:
        if user.role not in ("landlord", "agent"):
            raise HTTPException(status_code=403, detail="Only Landlord or Agent accounts can list Rent or Short-let properties.")
        if user.kyc_status != "approved":
            raise HTTPException(status_code=403, detail="Your account isn't verified yet — complete document verification before you can list a property.")

    listing = models.Listing(
        type=body.type, owner_id=user.id, title=body.title, description=body.description,
        state=body.state, lga=body.lga, beds=body.beds, baths=body.baths, amenities=body.amenities,
        annual_rent=body.annual_rent, caution_fee=body.caution_fee, service_charge=body.service_charge,
        agency_fee=body.agency_fee, nightly_rate=body.nightly_rate, total_rent=body.total_rent,
        roommate_share=body.roommate_share, gender_preference=body.gender_preference,
        house_rules=body.house_rules, available_from=body.available_from, status="pending_review",
    )
    db.add(listing)
    db.flush()
    for i, url in enumerate(body.photo_urls):
        db.add(models.ListingPhoto(listing_id=listing.id, url=url, position=i))
    db.commit()
    db.refresh(listing)
    return {"listing": _listing_out(listing, db)}


@router.get("")
def search_listings(
    type: Optional[str] = None, state: Optional[str] = None, lga: Optional[str] = None,
    min_beds: Optional[int] = None, max_price: Optional[float] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Listing).filter(models.Listing.status == "live")
    if type:
        q = q.filter(models.Listing.type == type)
    if state:
        q = q.filter(models.Listing.state == state)
    if lga:
        q = q.filter(models.Listing.lga == lga)
    if min_beds:
        q = q.filter(models.Listing.beds >= min_beds)
    if max_price:
        q = q.filter(
            (models.Listing.annual_rent <= max_price)
            | (models.Listing.nightly_rate <= max_price)
            | (models.Listing.roommate_share <= max_price)
        )
    listings = q.order_by(models.Listing.created_at.desc()).all()
    return {"listings": [_listing_out(l, db) for l in listings]}


@router.get("/mine")
def my_listings(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    listings = db.query(models.Listing).filter(models.Listing.owner_id == user.id).order_by(models.Listing.created_at.desc()).all()
    return {"listings": [_listing_out(l, db) for l in listings]}


@router.get("/{listing_id}")
def get_listing(listing_id: str, user=Depends(current_user_optional), db: Session = Depends(get_db)):
    listing = db.query(models.Listing).filter(models.Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")
    is_owner = user and user.id == listing.owner_id
    is_admin = user and user.role == "admin"
    if listing.status != "live" and not is_owner and not is_admin:
        raise HTTPException(status_code=404, detail="Listing not found.")

    other_listings = (
        db.query(models.Listing)
        .filter(models.Listing.owner_id == listing.owner_id, models.Listing.status == "live", models.Listing.id != listing.id)
        .limit(6).all()
    )
    out = _listing_out(listing, db)
    out["owner_other_listings"] = [_listing_out(l, db) for l in other_listings]
    return {"listing": out}
