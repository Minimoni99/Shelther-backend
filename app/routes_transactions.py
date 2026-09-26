import datetime
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from . import models, schemas
from .database import get_db
from .auth import current_user

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _price_and_breakdown(listing: models.Listing):
    if listing.type == "rent":
        items = {
            "Annual rent": float(listing.annual_rent or 0),
            "Agent fee": float(listing.agency_fee or 0),
            "Legal fee": float(listing.legal_fee or 0),
        }
        if listing.caution_fee:
            items["Caution fee"] = float(listing.caution_fee)
        if listing.service_charge:
            items["Service charge"] = float(listing.service_charge)
    elif listing.type == "shortlet":
        items = {"Nightly rate": float(listing.nightly_rate or 0)}
    else:
        items = {"Monthly share": float(listing.roommate_share or 0)}
    return sum(items.values()), items


@router.post("")
def create_transaction(body: schemas.TransactionCreateBody, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """DUMMY escrow checkout — instantly marks the payment HELD, exactly
    like a successful Paystack/Flutterwave charge would, but with no real
    gateway call. Swap the body of this function for a real charge later;
    the HELD/RELEASED/REFUNDED state machine below doesn't need to change."""
    listing = db.query(models.Listing).filter(models.Listing.id == body.listing_id, models.Listing.status == "live").first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found or not available.")
    if body.payment_method not in ("card", "bank_transfer"):
        raise HTTPException(status_code=400, detail="payment_method must be card or bank_transfer.")

    # Rent and Roommate require an approved in-person checkout first — Short-let
    # stays instant-pay since it's typically booked remotely without a viewing.
    if listing.type in ("rent", "roommate"):
        approved = (
            db.query(models.MeetingRequest)
            .filter(
                models.MeetingRequest.listing_id == listing.id,
                models.MeetingRequest.requester_id == user.id,
                models.MeetingRequest.status == "approved",
            )
            .first()
        )
        if not approved:
            raise HTTPException(
                status_code=403,
                detail="Complete an in-person checkout with the lister before paying — request a meeting first.",
            )

    amount, breakdown = _price_and_breakdown(listing)
    txn = models.Transaction(
        listing_id=listing.id, renter_id=user.id, amount=amount,
        breakdown=json.dumps(breakdown), payment_method=body.payment_method, status="held",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return {"transaction": _txn_out(txn)}


@router.post("/{transaction_id}/confirm-move-in")
def confirm_move_in(transaction_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """Renter confirms move-in / check-in → funds release to the host.
    DUMMY: just flips the ledger state; a real payout to the landlord's
    NUBAN happens later once Paystack/Flutterwave transfers are wired up."""
    txn = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    if txn.renter_id != user.id:
        raise HTTPException(status_code=403, detail="Not your transaction.")
    if txn.status != "held":
        raise HTTPException(status_code=400, detail=f"Transaction is already {txn.status}.")
    txn.status = "released"
    txn.released_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(txn)
    return {"transaction": _txn_out(txn)}


@router.get("/mine")
def my_transactions(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    txns = db.query(models.Transaction).filter(models.Transaction.renter_id == user.id).order_by(models.Transaction.created_at.desc()).all()
    return {"transactions": [_txn_out(t) for t in txns]}


def _txn_out(t: models.Transaction) -> dict:
    return {
        "id": t.id, "listing_id": t.listing_id, "amount": float(t.amount),
        "breakdown": json.loads(t.breakdown) if t.breakdown else {},
        "payment_method": t.payment_method, "status": t.status,
        "created_at": t.created_at.isoformat(),
        "released_at": t.released_at.isoformat() if t.released_at else None,
    }
