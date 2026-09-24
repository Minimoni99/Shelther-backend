import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from . import models
from .database import get_db
from .auth import require_role

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))])


@router.get("/kyc-documents")
def list_kyc_documents(status: str = "pending", db: Session = Depends(get_db)):
    docs = db.query(models.KycDocument).filter(models.KycDocument.status == status).order_by(models.KycDocument.uploaded_at.desc()).all()
    out = []
    for d in docs:
        owner = db.query(models.User).filter(models.User.id == d.user_id).first()
        out.append({
            "id": d.id, "doc_type": d.doc_type, "file_url": d.file_url, "status": d.status,
            "uploaded_at": d.uploaded_at.isoformat(),
            "user": {"id": owner.id, "name": owner.name, "role": owner.role} if owner else None,
        })
    return {"documents": out}


@router.post("/kyc-documents/{doc_id}/approve")
def approve_kyc(doc_id: str, admin=Depends(require_role("admin")), db: Session = Depends(get_db)):
    doc = db.query(models.KycDocument).filter(models.KycDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    doc.status = "approved"
    doc.reviewed_at = datetime.datetime.utcnow()
    doc.reviewed_by = admin.id
    # If this user now has both required documents approved, mark them fully verified.
    owner = db.query(models.User).filter(models.User.id == doc.user_id).first()
    approved_types = {
        d.doc_type for d in db.query(models.KycDocument).filter(
            models.KycDocument.user_id == owner.id, models.KycDocument.status == "approved"
        ).all()
    } | {doc.doc_type}
    if {"government_id", "agency_license_or_cofo"}.issubset(approved_types):
        owner.kyc_status = "approved"
    db.commit()
    return {"ok": True}


@router.post("/kyc-documents/{doc_id}/reject")
def reject_kyc(doc_id: str, admin=Depends(require_role("admin")), db: Session = Depends(get_db)):
    doc = db.query(models.KycDocument).filter(models.KycDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    doc.status = "rejected"
    doc.reviewed_at = datetime.datetime.utcnow()
    doc.reviewed_by = admin.id
    owner = db.query(models.User).filter(models.User.id == doc.user_id).first()
    owner.kyc_status = "rejected"
    db.commit()
    return {"ok": True}


@router.get("/listings")
def list_listings_for_review(status: str = "pending_review", db: Session = Depends(get_db)):
    listings = db.query(models.Listing).filter(models.Listing.status == status).order_by(models.Listing.created_at.desc()).all()
    out = []
    for l in listings:
        out.append({
            "id": l.id, "type": l.type, "title": l.title, "state": l.state, "lga": l.lga,
            "status": l.status, "owner_id": l.owner_id, "owner_name": l.owner.name,
            "owner_role": l.owner.role, "owner_kyc_status": l.owner.kyc_status,
            "photo_count": len(l.photos),
        })
    return {"listings": out}


@router.post("/listings/{listing_id}/approve")
def approve_listing(listing_id: str, db: Session = Depends(get_db)):
    listing = db.query(models.Listing).filter(models.Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")
    if listing.type in ("rent", "shortlet") and listing.owner.kyc_status != "approved":
        raise HTTPException(status_code=400, detail="Owner's KYC must be approved before this listing can go live.")
    listing.status = "live"
    db.commit()
    return {"ok": True}


@router.post("/listings/{listing_id}/reject")
def reject_listing(listing_id: str, db: Session = Depends(get_db)):
    listing = db.query(models.Listing).filter(models.Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")
    listing.status = "suspended"
    db.commit()
    return {"ok": True}


@router.get("/stats")
def admin_stats(db: Session = Depends(get_db)):
    return {
        "totalUsers": db.query(models.User).count(),
        "totalListings": db.query(models.Listing).count(),
        "liveListings": db.query(models.Listing).filter(models.Listing.status == "live").count(),
        "pendingListings": db.query(models.Listing).filter(models.Listing.status == "pending_review").count(),
        "pendingKyc": db.query(models.User).filter(models.User.kyc_status == "pending").count(),
        "heldInEscrow": float(
            sum((t.amount for t in db.query(models.Transaction).filter(models.Transaction.status == "held").all()), 0)
        ),
    }
