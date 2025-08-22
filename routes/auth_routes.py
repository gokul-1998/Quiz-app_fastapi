from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from fastapi import Response, Request

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
    response: Response = None
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

    # Set tokens as HttpOnly SESSION cookies (no max-age/expires) so they are cleared on browser close.
    # NOTE: Set secure=True in production (HTTPS) and adjust samesite as needed.
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax")

    # Return tokens in body for backward compatibility with existing tests/clients
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}



@router.post("/refresh", response_model=Token)
def refresh(
    request: Request,
    response: Response,
    token_data: Optional[TokenRefresh] = None,
    refresh_token: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Issue a new access token from a valid refresh token.
    - Reads refresh token from HttpOnly cookie by default.
    - Falls back to JSON body or query param for compatibility.
    - Does NOT require a valid access token (works when access is expired).
    """
    cookie_refresh = request.cookies.get("refresh_token")
    effective_refresh = cookie_refresh or (token_data.refresh_token if token_data else None) or refresh_token
    if not effective_refresh:
        raise HTTPException(status_code=400, detail="Missing refresh_token")

    payload = decode_token(effective_refresh)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if user.refresh_token != effective_refresh:
        raise HTTPException(status_code=401, detail="Refresh token mismatch")

    new_access = create_access_token({"sub": user.email, "type": "access"})
    # Refresh token is per-login; keep it stable until logout/login (no rotation here).
    response.set_cookie(key="access_token", value=new_access, httponly=True, secure=False, samesite="lax")
    return {"access_token": new_access, "token_type": "bearer", "refresh_token": effective_refresh}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Invalidate current session by revoking stored refresh token and clearing cookies.
    If a valid refresh token cookie exists and matches a user, revoke it; otherwise just clear cookies.
    """
    refresh_cookie = request.cookies.get("refresh_token")
    if refresh_cookie:
        payload = decode_token(refresh_cookie)
        if payload and payload.get("type") == "refresh":
            user = db.query(User).filter(User.email == payload.get("sub")).first()
            if user and user.refresh_token == refresh_cookie:
                user.refresh_token = None
                db.merge(user)
                db.commit()

    # Clear cookies by setting empty value and Max-Age=0
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Logged out"}
