from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from . import models, schemas
from .database import get_db
from .auth import current_user

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


@router.post("/listings/{listing_id}/request-meeting")
def request_meeting(listing_id: str, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    listing = db.query(models.Listing).filter(models.Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")
    req = models.MeetingRequest(listing_id=listing_id, requester_id=user.id)
    db.add(req)
    db.commit()
    db.refresh(req)
    return {"request": {"id": req.id, "status": req.status}}


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
