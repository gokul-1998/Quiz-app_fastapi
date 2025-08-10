import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set environment variables for testing
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["JWT_SECRET"] = "test_secret"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "15"
os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "7"

from main import app
from db import Base, get_db


# Setup the Test Database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Override the get_db dependency to use the test database
Base.metadata.create_all(bind=engine)


def override_get_db():
    try:  # pragma: no cover
        db = TestingSessionLocal()  # pragma: no cover
        yield db  # pragma: no cover
    finally:
        db.close()  # pragma: no cover


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
def client():
    # Create the tables
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    # Drop the tables
    Base.metadata.drop_all(bind=engine)
