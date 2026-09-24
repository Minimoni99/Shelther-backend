import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from . import (
    routes_auth, routes_lister, routes_listings, routes_messages,
    routes_transactions, routes_admin, routes_uploads,
)

# Creates tables on first run if they don't exist yet. Fine for now —
# once this has real production data, switch to Alembic migrations
# instead of relying on create_all for schema changes.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Shelther API")

allowed_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.environ.get("UPLOAD_DIR") or os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(routes_auth.router)
app.include_router(routes_lister.router)
app.include_router(routes_listings.router)
app.include_router(routes_messages.router)
app.include_router(routes_transactions.router)
app.include_router(routes_admin.router)
app.include_router(routes_uploads.router)


@app.get("/health")
def health():
    return {"ok": True}
