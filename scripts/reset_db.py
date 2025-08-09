#!/usr/bin/env python3
"""
DANGER: Drops and recreates all tables based on current SQLAlchemy models.
Use only in development. This will ERASE all existing data in those tables.
"""
import sys
from pathlib import Path

# Ensure project root is on sys.path so we can import db.py
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import Base, engine

if __name__ == "__main__":
    print("[reset_db] Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("[reset_db] Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("[reset_db] Done.")
