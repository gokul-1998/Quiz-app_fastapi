from typing import List, Optional, Union, Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel, Field
try:
    # Pydantic v2
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover
    ConfigDict = None  # type: ignore
from pydantic import field_validator
from sqlalchemy.orm import Session
import json
from datetime import datetime
from db import get_db, Deck, Card, DeckFavorite, DeckLike
from sqlalchemy import func
from routes.auth_routes import get_current_user

router = APIRouter(prefix="/decks", tags=["decks"])


# ----- Pydantic Schemas -----
class DeckBase(BaseModel):
    title: str
    description: Optional[str] = None
    tags: Optional[str] = Field(None, example="python,programming")  # Comma-separated
    visibility: Literal["public", "private"] = "private"

class DeckCreate(DeckBase):
    pass


class DeckUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    visibility: Optional[Literal["public", "private"]] = None


class CardBase(BaseModel):
    question: str
    answer: str


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


class MatchPair(BaseModel):
    left: str
    right: str


class CardCreateMatch(CardBase):
    qtype: Literal["match"]
    pairs: List[MatchPair]

    @field_validator("pairs")
    @classmethod
    def validate_pairs(cls, v: List[MatchPair]):
        if not isinstance(v, list) or len(v) != 4:
            raise ValueError("For match, exactly 4 pairs are required")
        for p in v:
            if not p.left or not p.right:
                raise ValueError("Each match pair must have non-empty 'left' and 'right'")
        return v

    if ConfigDict:
        model_config = ConfigDict(
            json_schema_extra={
                "examples": [
                    {
                        "qtype": "match",
                        "question": "Match countries to capitals",
                        "answer": "",
                        "pairs": [
                            {"left": "France", "right": "Paris"},
                            {"left": "Japan", "right": "Tokyo"},
                            {"left": "India", "right": "New Delhi"},
                            {"left": "USA", "right": "Washington, D.C."}
                        ]
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
    # For mcq: List[str]
    # For match: List[{"left": str, "right": str}] (shuffled order)
    options: Optional[List] = None

    model_config = ConfigDict(from_attributes=True)


class CardUpdate(BaseModel):
    """Partial update for a card. If qtype changes to 'mcq', options must be provided."""
    question: Optional[str] = None
    answer: Optional[str] = None
    qtype: Optional[Literal["mcq", "fillups", "match"]] = None
    options: Optional[List[str]] = None


class DeckOut(DeckBase):
    id: int
    owner_id: int
    created_at: datetime
    card_count: int | None = None  # Will be populated in list_decks
    favourite: bool = False  # Per-user flag
    like_count: int = 0  # Total likes
    liked: bool = False   # Whether current user liked

    class Config:
        orm_mode = True


# ----- Deck CRUD -----

@router.get("/my", response_model=List[DeckOut])
def list_my_decks(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Return all decks (public and private) owned by the current user."""
    decks = db.query(Deck).filter(Deck.owner_id == current_user.id).order_by(Deck.created_at.desc()).all()
    out = []
    for d in decks:
        card_count = db.query(Card).filter(Card.deck_id == d.id).count()
        out.append(DeckOut(
            id=d.id,
            title=d.title,
            description=d.description,
            tags=d.tags,
            visibility=d.visibility,
            owner_id=d.owner_id,
            created_at=d.created_at,
            card_count=card_count,
            favourite=False,
            like_count=0,
            liked=False
        ))
    return out

@router.get("/public", response_model=List[DeckOut])
def list_all_public_decks(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Return all public decks from all users."""
    decks = db.query(Deck).filter(Deck.visibility == "public").order_by(Deck.created_at.desc()).all()
    out = []
    for d in decks:
        card_count = db.query(Card).filter(Card.deck_id == d.id).count()
        out.append(DeckOut(
            id=d.id,
            title=d.title,
            description=d.description,
            tags=d.tags,
            visibility=d.visibility,
            owner_id=d.owner_id,
            created_at=d.created_at,
            card_count=card_count,
            favourite=False,
            like_count=0,
            liked=False
        ))
    return out

@router.post("/", response_model=DeckOut, status_code=status.HTTP_201_CREATED)
def create_deck(payload: DeckCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Create a new deck with optional tags and visibility."""
    deck = Deck(
        title=payload.title,
        description=payload.description,
        tags=payload.tags,
        visibility=payload.visibility,
        owner_id=current_user.id
    )
    db.add(deck)
    db.commit()
    db.refresh(deck)
    return deck


@router.get("/", response_model=List[DeckOut])
def list_decks(
    search: str | None = None,
    tag: str | None = None,
    page: int = 1,
    size: int = 10,
    response: Response = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """List all public decks from all users, plus all private decks owned by the current user. Does not return private decks of other users."""
    query = db.query(Deck).filter(
        (Deck.visibility == "public") |
        ((Deck.visibility == "private") & (Deck.owner_id == current_user.id))
    )
    if search:
        query = query.filter(Deck.title.ilike(f"%{search}%"))
    if tag:
        query = query.filter(Deck.tags.ilike(f"%{tag}%"))
    decks = query.order_by(Deck.created_at.desc()).offset((page-1)*size).limit(size).all()
    out = []
    for d in decks:
        card_count = db.query(Card).filter(Card.deck_id == d.id).count()
        out.append(DeckOut(
            id=d.id,
            title=d.title,
            description=d.description,
            tags=d.tags,
            visibility=d.visibility,
            owner_id=d.owner_id,
            created_at=d.created_at,
            card_count=card_count,
            favourite=False,
            like_count=0,
            liked=False
        ))
    return out

    
    # Apply search across title, description, and tags
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Deck.title.ilike(search_term)) |
            (Deck.description.ilike(search_term)) |
            (Deck.tags.ilike(search_term))
        )
    
    # Filter by tag (comma-separated)
    if tag:
        tags = [t.strip() for t in tag.split(",") if t.strip()]
        for t in tags:
            query = query.filter(Deck.tags.ilike(f"%{t}%"))
    
    # Filter by visibility if not "all"
    if visibility in ["public", "private"]:
        query = query.filter(Deck.visibility == visibility)
    
    # Like counts subquery for ordering and counts
    like_counts_subq = (
        db.query(DeckLike.deck_id.label("deck_id"), func.count(DeckLike.id).label("like_count"))
        .group_by(DeckLike.deck_id)
        .subquery()
    )

    # Total count using current filters
    count_subq = query.with_entities(Deck.id).subquery()
    total = db.query(func.count()).select_from(count_subq).scalar() or 0

    # Pagination
    page = max(1, page)
    size = max(1, min(size, 100))
    offset = (page - 1) * size

    # Order by like_count desc then id desc, then paginate
    query = (
        query.outerjoin(like_counts_subq, Deck.id == like_counts_subq.c.deck_id)
        .add_columns(func.coalesce(like_counts_subq.c.like_count, 0).label("like_count"))
        .order_by(func.coalesce(like_counts_subq.c.like_count, 0).desc(), Deck.id.desc())
        .offset(offset)
        .limit(size)
    )
    rows = query.all()
    decks = [row[0] for row in rows]
    like_counts_map = {row[0].id: row[1] for row in rows}

    # Favourite/Like flags and card counts for current user
    deck_ids = [d.id for d in decks]
    fav_rows = []
    if deck_ids:
        fav_rows = db.query(DeckFavorite.deck_id).filter(DeckFavorite.user_id == current_user.id, DeckFavorite.deck_id.in_(deck_ids)).all()
    fav_ids = {row[0] for row in fav_rows}

    liked_rows = []
    if deck_ids:
        liked_rows = db.query(DeckLike.deck_id).filter(DeckLike.user_id == current_user.id, DeckLike.deck_id.in_(deck_ids)).all()
    liked_ids = {row[0] for row in liked_rows}

    # Card counts per deck
    counts = {}
    if deck_ids:
        count_rows = (
            db.query(Card.deck_id, func.count(Card.id))
            .filter(Card.deck_id.in_(deck_ids))
            .group_by(Card.deck_id)
            .all()
        )
        counts = {deck_id: count for deck_id, count in count_rows}

    # Set pagination headers
    if response is not None:
        total_pages = (total + size - 1) // size
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(size)
        response.headers["X-Total-Pages"] = str(total_pages)

    # Build output with favourite/liked and like_count
    out: List[DeckOut] = []
    for d in decks:
        # card_count is not explicitly computed here; left None or could be computed via len(d.cards)
        out.append(
            DeckOut(
                id=d.id,
                title=d.title,
                description=d.description,
                tags=getattr(d, "tags", None),
                visibility=d.visibility,
                owner_id=d.owner_id,
                created_at=d.created_at,
                card_count=counts.get(d.id, 0),
                favourite=d.id in fav_ids,
                like_count=like_counts_map.get(d.id, 0),
                liked=d.id in liked_ids,
            )
        )
    return out


@router.post("/{deck_id}/like", status_code=status.HTTP_204_NO_CONTENT)
def like_deck(deck_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    deck = db.query(Deck).filter(Deck.id == deck_id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    # Any authenticated user can like any deck; owner can like too
    exists = db.query(DeckLike).filter(DeckLike.user_id == current_user.id, DeckLike.deck_id == deck_id).first()
    if not exists:
        db.add(DeckLike(user_id=current_user.id, deck_id=deck_id))
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{deck_id}/like", status_code=status.HTTP_204_NO_CONTENT)
def unlike_deck(deck_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    row = db.query(DeckLike).filter(DeckLike.user_id == current_user.id, DeckLike.deck_id == deck_id).first()
    if not row:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/{deck_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
def favorite_deck(deck_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    deck = db.query(Deck).filter(Deck.id == deck_id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    # Anyone can favorite a public deck; only owner can favorite private deck they own
    if deck.visibility != "public" and deck.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot favorite a private deck you do not own")
    exists = db.query(DeckFavorite).filter(DeckFavorite.user_id == current_user.id, DeckFavorite.deck_id == deck_id).first()
    if not exists:
        fav = DeckFavorite(user_id=current_user.id, deck_id=deck_id)
        db.add(fav)
        db.commit()
    return None

@router.delete("/{deck_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
def unfavorite_deck(deck_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    fav = db.query(DeckFavorite).filter(DeckFavorite.user_id == current_user.id, DeckFavorite.deck_id == deck_id).first()
    if fav:
        db.delete(fav)
        db.commit()
    return None


@router.get("/{deck_id}", response_model=DeckOut)
def get_deck(deck_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # Fetch by id first
    deck = db.query(Deck).filter(Deck.id == deck_id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    # Allow access if owner or deck is public
    is_owner = deck.owner_id == current_user.id
    if not is_owner and deck.visibility != "public":
        raise HTTPException(status_code=403, detail="Deck is private")
    return deck


@router.patch("/{deck_id}", response_model=DeckOut)
def update_deck(deck_id: int, payload: DeckUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Update a deck's details, including tags and visibility."""
    deck = db.query(Deck).filter(Deck.id == deck_id, Deck.owner_id == current_user.id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    
    update_data = payload.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(deck, field, value)
    
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
    # Only the deck owner can add cards
    deck = db.query(Deck).filter(Deck.id == deck_id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if deck.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to add cards to this deck")
    # persist options for MCQ or MATCH as JSON
    options_json = None
    if isinstance(payload, CardCreateMCQ):
        options_json = json.dumps(payload.options)
    elif isinstance(payload, CardCreateMatch):
        # store as list of {left,right}
        options_json = json.dumps([p.dict() for p in payload.pairs])
    card = Card(
        deck_id=deck.id,
        question=payload.question,
        answer=payload.answer,
        qtype=str(payload.qtype),
        options_json=options_json,
        visibility=deck.visibility,  # cards inherit deck visibility
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    # build response with decoded options if present
    # Build response; shuffle order for match
    opts = json.loads(card.options_json) if card.options_json else None
    if card.qtype == "match" and isinstance(opts, list):
        import random
        random.shuffle(opts)
    return CardOut(
        id=card.id,
        question=card.question,
        answer=card.answer,
        qtype=card.qtype,  # already a string literal value
        options=opts,
    )


@router.get("/{deck_id}/cards", response_model=List[CardOut])
def list_cards(deck_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    deck = db.query(Deck).filter(Deck.id == deck_id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    # Only allow non-owners to view cards if the deck is public
    is_owner = deck.owner_id == current_user.id
    if not is_owner and deck.visibility != "public":
        raise HTTPException(status_code=403, detail="Deck is private")
    # If the deck is public or owner, show cards; otherwise it's already forbidden
    cards = db.query(Card).filter(Card.deck_id == deck.id).all()
    out: List[CardOut] = []
    for c in cards:
        opts = json.loads(c.options_json) if c.options_json else None
        if c.qtype == "match" and isinstance(opts, list):
            import random
            random.shuffle(opts)
        out.append(
            CardOut(
                id=c.id,
                question=c.question,
                answer=c.answer,
                qtype=c.qtype,
                options=opts,
            )
        )
    return out


@router.get("/{deck_id}/cards/{card_id}", response_model=CardOut)
def get_card(deck_id: int, card_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    deck = db.query(Deck).filter(Deck.id == deck_id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    card = db.query(Card).filter(Card.id == card_id, Card.deck_id == deck_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    is_owner = deck.owner_id == current_user.id
    if not is_owner and deck.visibility != "public":
        raise HTTPException(status_code=403, detail="Not authorized to view this card")
    opts = json.loads(card.options_json) if card.options_json else None
    if card.qtype == "match" and isinstance(opts, list):
        import random
        random.shuffle(opts)
    return CardOut(
        id=card.id,
        question=card.question,
        answer=card.answer,
        qtype=card.qtype,
        options=opts,
    )


@router.patch("/{deck_id}/cards/{card_id}", response_model=CardOut)
def update_card(
    deck_id: int,
    card_id: int,
    payload: CardUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    deck = db.query(Deck).filter(Deck.id == deck_id, Deck.owner_id == current_user.id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found or not owned by user")
    card = db.query(Card).filter(Card.id == card_id, Card.deck_id == deck_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    data = payload.dict(exclude_unset=True)
    # Handle qtype/options together
    new_qtype = data.get("qtype", card.qtype)
    if "options" in data and (new_qtype not in ("mcq", "match")):
        raise HTTPException(status_code=400, detail="Options are only valid for mcq or match cards")
    if new_qtype == "mcq":
        opts = data.get("options")
        if opts is not None:
            # Validate mcq options (>=4 non-empty strings)
            if not isinstance(opts, list) or len(opts) < 4 or any((not isinstance(o, str) or not o.strip()) for o in opts):
                raise HTTPException(status_code=400, detail="For mcq, options must include at least 4 non-empty strings")
            card.options_json = json.dumps(opts)
        # If switching to mcq and no options provided, keep existing if present; else error
        if card.options_json is None and opts is None:
            raise HTTPException(status_code=400, detail="mcq requires 'options' with at least 4 items")
    elif new_qtype == "match":
        opts = data.get("options")
        if opts is not None:
            # Expect exactly 4 pairs of {left,right}
            if not isinstance(opts, list) or len(opts) != 4:
                raise HTTPException(status_code=400, detail="For match, exactly 4 pairs are required in 'options'")
            for p in opts:
                if not isinstance(p, dict) or not p.get("left") or not p.get("right"):
                    raise HTTPException(status_code=400, detail="Each match pair must be an object with non-empty 'left' and 'right'")
            card.options_json = json.dumps(opts)
        if card.options_json is None and opts is None:
            raise HTTPException(status_code=400, detail="match requires 'options' as exactly 4 pairs")
    else:
        # Non-mcq/match cards should not keep options
        card.options_json = None

    # Update simple fields
    for field in ["question", "answer", "qtype"]:
        if field in data:
            setattr(card, field, data[field])

    db.commit()
    db.refresh(card)
    return CardOut(
        id=card.id,
        question=card.question,
        answer=card.answer,
        qtype=card.qtype,
        options=json.loads(card.options_json) if card.options_json else None,
        visibility=card.visibility,
    )


@router.delete("/{deck_id}/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(deck_id: int, card_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    deck = db.query(Deck).filter(Deck.id == deck_id, Deck.owner_id == current_user.id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found or not owned by user")
    card = db.query(Card).filter(Card.id == card_id, Card.deck_id == deck_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    db.delete(card)
    db.commit()
    return None
