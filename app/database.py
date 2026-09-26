import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Railway's managed Postgres provides DATABASE_URL automatically once the
# plugin is attached. Falls back to a local SQLite file for dev/testing
# here in the sandbox, so the same code runs in both places.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./shelther_dev.db")

# Railway's Postgres URL sometimes starts with postgres:// — SQLAlchemy 2.x
# requires postgresql://. It can also come as postgresql+psycopg:// (driver
# v3) or with no driver suffix at all, and which one SQLAlchemy tries to
# import isn't fully predictable across environments — so rather than
# install every possible driver, force a known-good one (psycopg2)
# explicitly here.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql+psycopg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
