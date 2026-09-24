import os
import jwt
import datetime
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session
from . import models
from .database import get_db

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGO = "HS256"
TOKEN_DAYS = 30


def sign(user: models.User) -> str:
    payload = {
        "id": user.id,
        "role": user.role,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=TOKEN_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")


def current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> models.User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not signed in.")
    payload = _decode(authorization.split(" ", 1)[1])
    user = db.query(models.User).filter(models.User.id == payload["id"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    return user


def current_user_optional(authorization: str = Header(None), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        payload = _decode(authorization.split(" ", 1)[1])
    except HTTPException:
        return None
    return db.query(models.User).filter(models.User.id == payload["id"]).first()


def require_role(*roles):
    def dep(user: models.User = Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Not allowed for your account type.")
        return user
    return dep
