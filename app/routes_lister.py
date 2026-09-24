from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from . import models, schemas
from .database import get_db
from .auth import current_user, require_role, sign
import uuid
import os
import datetime
import bcrypt

router = APIRouter(prefix="/api/lister", tags=["lister"])

UPLOAD_DIR = os.environ.get("UPLOAD_DIR") or os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_DOC_EXT = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def _safe_lister(u: models.User) -> dict:
    return {
        "id": u.id, "name": u.name, "email": u.email, "phone": u.phone, "role": u.role,
        "state": u.state, "lga": u.lga, "business_name": u.business_name,
        "profile_photo_url": u.profile_photo_url, "kyc_status": u.kyc_status,
    }


@router.post("/register")
def register_lister(body: schemas.ListerRegisterBody, db: Session = Depends(get_db)):
    """Landlord/Agent accounts can be created immediately with no
    verification — name, state/LGA, business name (Agent only), phone,
    email, and a password. They can browse their own dashboard right
    away, but per the spec, listing creation itself stays blocked until
    kyc_status is 'approved' (enforced in routes_listings.create_listing)."""
    if body.role not in ("landlord", "agent"):
        raise HTTPException(status_code=400, detail="role must be landlord or agent.")

    existing = (
        db.query(models.User)
        .filter((models.User.email == body.email) | (models.User.phone == body.phone))
        .first()
    )
    if existing:
        if existing.password_hash:
            raise HTTPException(status_code=409, detail="An account with that email or phone already exists — sign in instead.")
        # Upgrade a lightweight browsing identity (no password yet) into a full Landlord/Agent account.
        user = existing
    else:
        user = models.User(email=body.email, phone=body.phone)
        db.add(user)

    user.role = body.role
    user.name = body.name
    user.state = body.state
    user.lga = body.lga
    user.business_name = body.business_name if body.role == "agent" else None
    user.password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    user.kyc_status = "none"
    db.commit()
    db.refresh(user)
    return {"token": sign(user), "user": _safe_lister(user)}


@router.post("/login")
def login_lister(body: schemas.ListerLoginBody, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user or not user.password_hash or not bcrypt.checkpw(body.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return {"token": sign(user), "user": _safe_lister(user)}


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
    if body.lasrera_id:
        user.lasrera_id = body.lasrera_id
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
