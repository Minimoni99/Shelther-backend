import datetime
import random
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from . import models, schemas
from .database import get_db
from .auth import sign, current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

OTP_TTL_MINUTES = 10
# DUMMY: every code is fixed for now so testing doesn't need a real phone/
# SMS provider. Swap this for a real generator + SMS send once ready —
# nothing else in the app needs to change.
DUMMY_CODE = "123456"


@router.post("/request-otp")
def request_otp(body: schemas.RequestOtpBody, db: Session = Depends(get_db)):
    code = DUMMY_CODE
    otp = models.OtpCode(
        identifier=body.identifier,
        code=code,
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(minutes=OTP_TTL_MINUTES),
    )
    db.add(otp)
    db.commit()
    # DUMMY: return the code directly instead of sending an SMS/email, so
    # the flow is testable end-to-end without a provider hooked up yet.
    return {"sent": True, "dummy_code": code, "note": "SMS/email not wired up yet — using a fixed test code."}


@router.post("/verify-otp")
def verify_otp(body: schemas.VerifyOtpBody, db: Session = Depends(get_db)):
    otp = (
        db.query(models.OtpCode)
        .filter(models.OtpCode.identifier == body.identifier, models.OtpCode.consumed == False)
        .order_by(models.OtpCode.created_at.desc())
        .first()
    )
    if not otp or otp.code != body.code:
        raise HTTPException(status_code=400, detail="Incorrect code.")
    if otp.expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="Code expired — request a new one.")

    otp.consumed = True

    is_phone = "@" not in body.identifier
    user = (
        db.query(models.User)
        .filter(models.User.phone == body.identifier if is_phone else models.User.email == body.identifier)
        .first()
    )
    if not user:
        user = models.User(
            phone=body.identifier if is_phone else None,
            email=body.identifier if not is_phone else None,
            name=body.name,
            role="light",
            is_phone_verified=is_phone,
            is_email_verified=not is_phone,
        )
        db.add(user)
    else:
        if body.name and not user.name:
            user.name = body.name
        if is_phone:
            user.is_phone_verified = True
        else:
            user.is_email_verified = True

    db.commit()
    db.refresh(user)
    return {"token": sign(user), "user": _safe_user(user)}


@router.get("/me")
def me(user: models.User = Depends(current_user)):
    return {"user": _safe_user(user)}


@router.put("/me")
def update_me(body: schemas.UpdateProfileBody, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if body.name is not None:
        user.name = body.name
    if body.bio is not None:
        user.bio = body.bio
    if body.profile_photo_url is not None:
        user.profile_photo_url = body.profile_photo_url
    db.commit()
    db.refresh(user)
    return {"user": _safe_user(user)}


def _safe_user(u: models.User) -> dict:
    return {
        "id": u.id,
        "phone": u.phone,
        "email": u.email,
        "name": u.name,
        "role": u.role,
        "profile_photo_url": u.profile_photo_url,
        "bio": u.bio,
        "kyc_status": u.kyc_status,
    }
