from typing import List, Optional, Union, Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
try:
    # Pydantic v2
    from pydantic import ConfigDict
except ImportError:  # fallback for v1 if present
    ConfigDict = None  # type: ignore
from pydantic import field_validator
from sqlalchemy.orm import Session
import json

from db import get_db, Deck, Card
from routes.auth_routes import get_current_user

router = APIRouter(prefix="/decks", tags=["decks"])


# ----- Pydantic Schemas -----
class DeckCreate(BaseModel):
    title: str
    description: Optional[str] = None


class DeckUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class CardBase(BaseModel):
    question: str
    answer: str
    visibility: Literal["public", "private"] = "private"


class CardCreateMCQ(CardBase):
    qtype: Literal["mcq"]
    options: List[str]

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: List[str]):
        if not isinstance(v, list) or len(v) < 4:
            raise ValueError("For mcq, options must include at least 4 items")
        if any((not isinstance(opt, str) or not opt.strip()) for opt in v):
            raise ValueError("All mcq options must be non-empty strings")
        return v
    if ConfigDict:
        model_config = ConfigDict(
            json_schema_extra={
                "examples": [
                    {
                        "qtype": "mcq",
                        "question": "Capital of France?",
                        "answer": "Paris",
                        "options": ["Paris", "London", "Berlin", "Rome"],
                    }
                ]
            }
        )


class CardCreateFillups(CardBase):
    qtype: Literal["fillups"]
    if ConfigDict:
        model_config = ConfigDict(
            json_schema_extra={
                "examples": [
                    {
                        "qtype": "fillups",
                        "question": "2 + 2 = ?",
                        "answer": "4",
                    }
                ]
            }
        )


class CardCreateMatch(CardBase):
    qtype: Literal["match"]
    if ConfigDict:
        model_config = ConfigDict(
            json_schema_extra={
                "examples": [
                    {
                        "qtype": "match",
                        "question": "Match country to capital: FR=?",
                        "answer": "FR=Paris",
                    }
                ]
            }
        )


# Discriminated union so Swagger shows schema per qtype
CardCreate = Annotated[Union[CardCreateMCQ, CardCreateFillups, CardCreateMatch], Field(discriminator="qtype")]


class CardOut(BaseModel):
    id: int
    question: str
    answer: str
    qtype: Literal["mcq", "match", "fillups"]
    options: Optional[List[str]] = None
    visibility: Literal["public", "private"]

    class Config:
        from_attributes = True


class DeckOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


# ----- Deck CRUD -----
@router.post("/", response_model=DeckOut, status_code=status.HTTP_201_CREATED)
def create_deck(payload: DeckCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    deck = Deck(title=payload.title, description=payload.description, owner_id=current_user.id)
    db.add(deck)
    db.commit()
    db.refresh(deck)
    return deck


@router.get("/", response_model=List[DeckOut])
def list_decks(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return db.query(Deck).filter(Deck.owner_id == current_user.id).all()


@router.get("/{deck_id}", response_model=DeckOut)
def get_deck(deck_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    deck = db.query(Deck).filter(Deck.id == deck_id, Deck.owner_id == current_user.id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    return deck


@router.patch("/{deck_id}", response_model=DeckOut)
def update_deck(deck_id: int, payload: DeckUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    deck = db.query(Deck).filter(Deck.id == deck_id, Deck.owner_id == current_user.id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if payload.title is not None:
        deck.title = payload.title
    if payload.description is not None:
        deck.description = payload.description
    db.commit()
    db.refresh(deck)
    return deck


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck(deck_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    deck = db.query(Deck).filter(Deck.id == deck_id, Deck.owner_id == current_user.id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    db.delete(deck)
    db.commit()
    return None


# ----- Cards within a deck -----
@router.post("/{deck_id}/cards", response_model=CardOut, status_code=status.HTTP_201_CREATED)
def add_card(deck_id: int, payload: CardCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    deck = db.query(Deck).filter(Deck.id == deck_id, Deck.owner_id == current_user.id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    # persist options for MCQ as JSON
    options_json = json.dumps(payload.options) if isinstance(payload, CardCreateMCQ) else None
    card = Card(
        deck_id=deck.id,
        question=payload.question,
        answer=payload.answer,
        qtype=str(payload.qtype),
        options_json=options_json,
        visibility=payload.visibility,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    # build response with decoded options if present
    return CardOut(
        id=card.id,
        question=card.question,
        answer=card.answer,
        qtype=card.qtype,  # already a string literal value
        options=json.loads(card.options_json) if card.options_json else None,
        visibility=card.visibility,
    )


@router.get("/{deck_id}/cards", response_model=List[CardOut])
def list_cards(deck_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    deck = db.query(Deck).filter(Deck.id == deck_id, Deck.owner_id == current_user.id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    # If the current user owns the deck, show all cards. Otherwise, show only public cards.
    if deck.owner_id == current_user.id:
        cards = db.query(Card).filter(Card.deck_id == deck.id).all()
    else:
        cards = db.query(Card).filter(Card.deck_id == deck.id, Card.visibility == "public").all()
    out: List[CardOut] = []
    for c in cards:
        out.append(
            CardOut(
                id=c.id,
                question=c.question,
                answer=c.answer,
                qtype=c.qtype,
                options=json.loads(c.options_json) if c.options_json else None,
                visibility=c.visibility,
            )
        )
    return out
