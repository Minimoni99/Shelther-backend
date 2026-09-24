from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from . import models, schemas
from .database import get_db
from .auth import current_user, require_role
import uuid
import os
import datetime

router = APIRouter(prefix="/api/lister", tags=["lister"])

UPLOAD_DIR = os.environ.get("UPLOAD_DIR") or os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_DOC_EXT = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


@router.post("/become")
def become_lister(body: schemas.BecomeListerBody, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    """Screen 5b step 1: role choice + profile creation. Profile photo is
    mandatory (enforced by requiring profile_photo_url), matching the
    'this is what renters see on your listings' requirement."""
    if body.role not in ("landlord", "agent"):
        raise HTTPException(status_code=400, detail="role must be landlord or agent.")
    if not body.profile_photo_url:
        raise HTTPException(status_code=400, detail="A profile photo is required.")

    user.role = body.role
    user.name = body.name
    user.email = body.email
    user.profile_photo_url = body.profile_photo_url
    user.kyc_status = "none"  # they'll upload documents next
    db.commit()
    db.refresh(user)
    return {"user": {"id": user.id, "role": user.role, "name": user.name, "kyc_status": user.kyc_status}}


@router.post("/upload-document")
async def upload_kyc_document(
    doc_type: str,
    file: UploadFile = File(...),
    user: models.User = Depends(require_role("landlord", "agent")),
    db: Session = Depends(get_db),
):
    """Screen 5b step 2: document verification. DUMMY — stores the file
    and marks it pending for manual admin review; no KYC vendor call."""
    if doc_type not in ("government_id", "agency_license_or_cofo"):
        raise HTTPException(status_code=400, detail="doc_type must be government_id or agency_license_or_cofo.")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_DOC_EXT:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, WEBP, or PDF documents are allowed.")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File is too large (max 15MB).")

    filename = f"{uuid.uuid4()}{ext}"
    with open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
        f.write(contents)

    doc = models.KycDocument(user_id=user.id, doc_type=doc_type, file_url=f"/uploads/{filename}")
    db.add(doc)
    user.kyc_status = "pending"
    db.commit()
    db.refresh(doc)
    return {"document": {"id": doc.id, "doc_type": doc.doc_type, "status": doc.status}}


@router.get("/kyc-status")
def kyc_status(user: models.User = Depends(require_role("landlord", "agent"))):
    return {"kyc_status": user.kyc_status}
