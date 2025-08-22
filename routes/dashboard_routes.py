from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
from datetime import datetime, timedelta
from db import get_db, Deck, Card, User, DeckLike, DeckFavorite
from routes.auth_routes import get_current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# ----- Dashboard Models -----

class PopularDeck(BaseModel):
    id: int
    title: str
    description: Optional[str]
    tags: Optional[str]
    owner_username: str
    card_count: int
    like_count: int
    created_at: datetime

class RecentActivity(BaseModel):
    type: str  # "deck_created", "card_added", "deck_liked"
    message: str
    timestamp: datetime
    deck_id: Optional[int] = None
    user: str

class DashboardStats(BaseModel):
    total_public_decks: int
    total_cards_available: int
    active_users: int
    popular_subjects: List[Dict[str, Any]]

# ----- Dashboard Endpoints -----

@router.get("/", response_model=Dict[str, Any])
def get_dashboard(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get dashboard overview with popular decks, stats, and activities."""
    
    # Get popular public decks (most liked)
    popular_decks_query = (
        db.query(
            Deck.id,
            Deck.title,
            Deck.description,
            Deck.tags,
            User.email.label("owner_username"),
            func.count(Card.id).label("card_count"),
            func.count(DeckLike.id).label("like_count"),
            Deck.created_at
        )
        .join(User, Deck.owner_id == User.id)
        .outerjoin(Card, Deck.id == Card.deck_id)
        .outerjoin(DeckLike, Deck.id == DeckLike.deck_id)
        .filter(Deck.visibility == "public")
        .group_by(Deck.id, User.email)
        .order_by(desc("like_count"), desc(Deck.created_at))
        .limit(10)
        .all()
    )
    
    popular_decks = [
        PopularDeck(
            id=deck.id,
            title=deck.title,
            description=deck.description,
            tags=deck.tags,
            owner_username=deck.owner_username,
            card_count=deck.card_count,
            like_count=deck.like_count,
            created_at=deck.created_at
        )
        for deck in popular_decks_query
    ]
    
    # Get dashboard statistics
    total_public_decks = db.query(Deck).filter(Deck.visibility == "public").count()
    total_cards = db.query(Card).join(Deck).filter(Deck.visibility == "public").count()
    active_users = db.query(User).count()
    
    # Get popular subjects from tags
    tag_counts = {}
    decks_with_tags = db.query(Deck.tags).filter(
        and_(Deck.tags.isnot(None), Deck.visibility == "public")
    ).all()
    
    for (tags,) in decks_with_tags:
        if tags:
            for tag in tags.split(","):
                tag = tag.strip().lower()
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    popular_subjects = [
        {"subject": tag, "count": count}
        for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    ]
    
    # Get recent activity (recent public decks created)
    recent_decks = (
        db.query(Deck, User.email)
        .join(User, Deck.owner_id == User.id)
        .filter(Deck.visibility == "public")
        .order_by(desc(Deck.created_at))
        .limit(5)
        .all()
    )
    
    recent_activities = [
        RecentActivity(
            type="deck_created",
            message=f"{username} created deck '{deck.title}'",
            timestamp=deck.created_at,
            deck_id=deck.id,
            user=username
        )
        for deck, username in recent_decks
    ]
    
    return {
        "popular_decks": popular_decks,
        "stats": DashboardStats(
            total_public_decks=total_public_decks,
            total_cards_available=total_cards,
            active_users=active_users,
            popular_subjects=popular_subjects
        ),
        "recent_activities": recent_activities,
        "user_info": {
            "username": current_user.email,
            "user_id": current_user.id
        }
    }

@router.get("/discover", include_in_schema=False)
def discover_decks(
    subject: Optional[str] = None,
    difficulty: Optional[str] = None,
    min_cards: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Discover new decks to test based on preferences."""
    
    query = (
        db.query(
            Deck.id,
            Deck.title,
            Deck.description,
            Deck.tags,
            User.email.label("owner_username"),
            func.count(Card.id).label("card_count"),
            Deck.created_at
        )
        .join(User, Deck.owner_id == User.id)
        .outerjoin(Card, Deck.id == Card.deck_id)
        .filter(Deck.visibility == "public")
        .filter(Deck.owner_id != current_user.id)  # Exclude user's own decks
        .group_by(Deck.id, User.email)
        .having(func.count(Card.id) >= min_cards)
    )
    
    if subject:
        query = query.filter(Deck.tags.contains(subject.lower()))
    
    # Order by recent and popular
    decks = query.order_by(desc(Deck.created_at)).limit(limit).all()
    
    return {
        "decks": [
            {
                "id": deck.id,
                "title": deck.title,
                "description": deck.description,
                "tags": deck.tags,
                "owner": deck.owner_username,
                "card_count": deck.card_count,
                "created_at": deck.created_at
            }
            for deck in decks
        ],
        "filters_applied": {
            "subject": subject,
            "difficulty": difficulty,
            "min_cards": min_cards
        }
    }

@router.get("/subjects", include_in_schema=False)
def get_available_subjects(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get all available subjects/tags from public decks."""
    
    decks_with_tags = db.query(Deck.tags).filter(
        and_(Deck.tags.isnot(None), Deck.visibility == "public")
    ).all()
    
    all_subjects = set()
    for (tags,) in decks_with_tags:
        if tags:
            for tag in tags.split(","):
                tag = tag.strip().lower()
                if tag:
                    all_subjects.add(tag)
    
    return {
        "subjects": sorted(list(all_subjects)),
        "total_subjects": len(all_subjects)
    }

@router.get("/quick-test", include_in_schema=False)
def get_quick_test_options(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get quick test options - random decks for immediate testing."""
    
    # Get 5 random public decks with at least 5 cards
    random_decks = (
        db.query(
            Deck.id,
            Deck.title,
            Deck.description,
            Deck.tags,
            User.email.label("owner_username"),
            func.count(Card.id).label("card_count")
        )
        .join(User, Deck.owner_id == User.id)
        .join(Card, Deck.id == Card.deck_id)
        .filter(Deck.visibility == "public")
        .filter(Deck.owner_id != current_user.id)
        .group_by(Deck.id, User.email)
        .having(func.count(Card.id) >= 5)
        .order_by(func.random())
        .limit(5)
        .all()
    )
    
    return {
        "quick_test_decks": [
            {
                "id": deck.id,
                "title": deck.title,
                "description": deck.description,
                "tags": deck.tags,
                "owner": deck.owner_username,
                "card_count": deck.card_count,
                "per_card_seconds": 10,
                "estimated_time": f"{deck.card_count * 10} seconds"  # 10 sec per card estimate
            }
            for deck in random_decks
        ]
    }
