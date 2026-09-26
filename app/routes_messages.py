from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from . import models, schemas
from .database import get_db
from .auth import current_user
import datetime

router = APIRouter(prefix="/api", tags=["messages"])


@router.post("/messages")
def send_message(body: schemas.MessageCreateBody, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    listing = db.query(models.Listing).filter(models.Listing.id == body.listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")
    if not user.name:
        raise HTTPException(status_code=400, detail="Add your name to your profile before messaging — it's what the other person sees.")
    msg = models.Message(listing_id=body.listing_id, sender_id=user.id, recipient_id=body.recipient_id, body=body.body)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"message": {"id": msg.id, "body": msg.body, "created_at": msg.created_at.isoformat()}}


@router.get("/messages/{listing_id}")
def thread(listing_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    msgs = (
        db.query(models.Message)
        .filter(
            models.Message.listing_id == listing_id,
            or_(models.Message.sender_id == user.id, models.Message.recipient_id == user.id),
        )
        .order_by(models.Message.created_at)
        .all()
    )
    return {
        "messages": [
            {"id": m.id, "sender_id": m.sender_id, "body": m.body, "created_at": m.created_at.isoformat()}
            for m in msgs
        ]
    }


MEETING_RESPONSE_WINDOW_HOURS = 48


def _meeting_out(r: models.MeetingRequest) -> dict:
    deadline = r.created_at + datetime.timedelta(hours=MEETING_RESPONSE_WINDOW_HOURS)
    is_expired = r.status == "pending" and datetime.datetime.utcnow() > deadline
    return {
        "id": r.id, "listing_id": r.listing_id, "requester_id": r.requester_id,
        "requester_name": r.requester_name, "requester_phone": r.requester_phone,
        "description": r.description,
        "meeting_date": r.meeting_date.isoformat() if r.meeting_date else None,
        "meeting_location": r.meeting_location,
        "status": "expired" if is_expired else r.status,
        "response_deadline": deadline.isoformat(),
        "created_at": r.created_at.isoformat(),
    }


@router.post("/listings/{listing_id}/request-meeting")
def request_meeting(listing_id: str, body: schemas.MeetingRequestBody, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """'Request meeting or In-person checkout'. The lister gets 48 hours to
    respond with a date and location — approving is what unlocks payment
    on Rent and Roommate listings (Short-let stays instant-pay)."""
    listing = db.query(models.Listing).filter(models.Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")
    req = models.MeetingRequest(
        listing_id=listing_id, requester_id=user.id,
        requester_name=body.name, requester_phone=body.phone, description=body.description,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return {"request": _meeting_out(req)}


@router.get("/listings/{listing_id}/my-meeting-request")
def my_meeting_request(listing_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """The requester's own latest meeting request for this listing, if any —
    used to decide whether the Pay button should be active."""
    req = (
        db.query(models.MeetingRequest)
        .filter(models.MeetingRequest.listing_id == listing_id, models.MeetingRequest.requester_id == user.id)
        .order_by(models.MeetingRequest.created_at.desc())
        .first()
    )
    return {"request": _meeting_out(req) if req else None}


@router.get("/lister/meeting-requests")
def lister_meeting_requests(status: str = "pending", user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """Meeting requests on the current user's own listings, for them to
    approve (with a date + location) or decline."""
    q = (
        db.query(models.MeetingRequest)
        .join(models.Listing, models.Listing.id == models.MeetingRequest.listing_id)
        .filter(models.Listing.owner_id == user.id)
    )
    if status != "all":
        q = q.filter(models.MeetingRequest.status == status)
    reqs = q.order_by(models.MeetingRequest.created_at.desc()).all()
    out = []
    for r in reqs:
        item = _meeting_out(r)
        item["listing_title"] = r.listing.title
        out.append(item)
    return {"requests": out}


@router.post("/meeting-requests/{request_id}/approve")
def approve_meeting(request_id: str, body: schemas.MeetingApproveBody, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    req = db.query(models.MeetingRequest).filter(models.MeetingRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Meeting request not found.")
    if req.listing.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not your listing.")
    req.meeting_date = body.meeting_date
    req.meeting_location = body.meeting_location
    req.status = "approved"
    req.responded_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(req)
    return {"request": _meeting_out(req)}


@router.post("/meeting-requests/{request_id}/decline")
def decline_meeting(request_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    req = db.query(models.MeetingRequest).filter(models.MeetingRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Meeting request not found.")
    if req.listing.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not your listing.")
    req.status = "declined"
    req.responded_at = datetime.datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/listings/{listing_id}/request-picture")
def request_picture(listing_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    listing = db.query(models.Listing).filter(models.Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")
    req = models.PictureRequest(listing_id=listing_id, requester_id=user.id)
    db.add(req)
    db.commit()
    db.refresh(req)
    return {"request": {"id": req.id, "status": req.status}}
