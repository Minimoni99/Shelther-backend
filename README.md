# Shelther Backend (Phase 1)

FastAPI + Postgres. Covers the full data model and business logic for
all 3 verticals (Rent, Short-let, Roommate) with dummy stand-ins for the
3 hard integrations, so the whole flow is testable before wiring in
real services:

- **OTP**: `request-otp` returns a fixed test code (`123456`) instead of
  sending a real SMS/email.
- **KYC**: Landlord/Agent documents upload and wait for an admin to
  manually approve/reject — no automated vendor call.
- **Escrow**: "Pay" instantly marks a transaction HELD; a renter
  confirming move-in marks it RELEASED — no real Paystack/Flutterwave
  call yet.

## Local setup
```
pip install -r requirements.txt --break-system-packages
python3 create_admin.py you@example.com "Your Name"
uvicorn app.main:app --reload
```

## Deploying
Same pattern as the Foundry backend: Railway, with a managed Postgres
add-on attached (sets `DATABASE_URL` automatically), plus `JWT_SECRET`,
`CORS_ORIGINS`, and `UPLOAD_DIR=/data/uploads` set manually, with a
volume mounted at `/data`.
