from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from db import get_db, User


class UserCreate(BaseModel):
    email: str
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class TokenRefresh(BaseModel):
    refresh_token: str


router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid access token")

    user = db.query(User).filter(User.email == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    hashed_pw = hash_password(user.password)
    new_user = User(email=user.email, hashed_password=hashed_pw)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User registered successfully"}


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token({"sub": user.email, "type": "access"})
    refresh_token = create_refresh_token({"sub": user.email, "type": "refresh"})
    user.refresh_token = refresh_token
    db.merge(user)
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/refresh")
def refresh(
    token_data: TokenRefresh,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    refresh_token = token_data.refresh_token
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if current_user.refresh_token != refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token mismatch")

    new_access = create_access_token({"sub": current_user.email, "type": "access"})
    return {"access_token": new_access, "token_type": "bearer", "refresh_token": refresh_token}
