"""Seed an admin user directly, bypassing the OTP flow. Run once:
    python3 create_admin.py <phone_or_email> "<Full Name>"
"""
import sys
sys.path.insert(0, ".")
from app.database import SessionLocal, Base, engine
from app import models

Base.metadata.create_all(bind=engine)

if len(sys.argv) < 3:
    print("Usage: python3 create_admin.py <phone_or_email> \"<Full Name>\"")
    sys.exit(1)

identifier, name = sys.argv[1], sys.argv[2]
is_phone = "@" not in identifier

db = SessionLocal()
existing = db.query(models.User).filter(
    models.User.phone == identifier if is_phone else models.User.email == identifier
).first()
if existing:
    existing.role = "admin"
    existing.name = name
    db.commit()
    print(f"Updated existing user {identifier} to admin.")
else:
    user = models.User(
        phone=identifier if is_phone else None,
        email=identifier if not is_phone else None,
        name=name, role="admin",
        is_phone_verified=is_phone, is_email_verified=not is_phone,
    )
    db.add(user)
    db.commit()
    print(f"Admin account created: {identifier}")
db.close()
