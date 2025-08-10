from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import json
from db import get_db, Deck, Card, User
from routes.auth_routes import get_current_user

router = APIRouter(prefix="/tests", tags=["testing"])

# ----- Test Session Models -----

class TestAnswer(BaseModel):
    card_id: int
    user_answer: str
    is_correct: bool
    time_taken: Optional[int] = None  # seconds

class TestSession(BaseModel):
    deck_id: int
    user_id: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_cards: int
    correct_answers: int = 0
    total_time: Optional[int] = None  # seconds
    answers: List[TestAnswer] = []

class TestSessionCreate(BaseModel):
    deck_id: int
    # Optional timing: defaults to 10s per card if total_time_seconds not provided
    per_card_seconds: int = 10
    total_time_seconds: Optional[int] = None

class TestAnswerSubmit(BaseModel):
    card_id: int
    user_answer: str
    time_taken: Optional[int] = None

class TestSessionResult(BaseModel):
    session_id: str
    deck_title: str
    deck_owner: str
    total_cards: int
    correct_answers: int
    accuracy: float
    total_time: Optional[int] = None
    completed_at: datetime
    answers: List[TestAnswer]

class TestStats(BaseModel):
    total_tests_taken: int
    total_decks_tested: int
    average_accuracy: float
    favorite_subjects: List[str]
    recent_tests: List[Dict[str, Any]]

# ----- Test Session Endpoints -----

@router.post("/start", response_model=Dict[str, Any])
def start_test_session(
    payload: TestSessionCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Start a new test session for a deck."""
    # Verify deck exists and is accessible
    deck = db.query(Deck).filter(Deck.id == payload.deck_id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    
    # Check if user can access this deck
    if deck.visibility == "private" and deck.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot access private deck")
    
    # Get all cards in the deck
    cards = db.query(Card).filter(Card.deck_id == payload.deck_id).all()
    if not cards:
        raise HTTPException(status_code=400, detail="Deck has no cards to test")
    
    # Create session ID (using timestamp + user_id for uniqueness)
    session_id = f"{current_user.id}_{payload.deck_id}_{int(datetime.now().timestamp())}"
    
    # Prepare cards for testing (without answers)
    test_cards = []
    for card in cards:
        card_data = {
            "id": card.id,
            "question": card.question,
            "qtype": card.qtype,
            "options": json.loads(card.options_json) if card.options_json else None
        }
        test_cards.append(card_data)
    
    # Determine timing
    per_card_seconds = payload.per_card_seconds
    time_limit_seconds = (
        payload.total_time_seconds
        if payload.total_time_seconds is not None
        else len(cards) * per_card_seconds
    )
    ends_at = datetime.now() + timedelta(seconds=time_limit_seconds)

    # Store session in memory/cache (in production, use Redis or database)
    # For now, we'll return the session info for the frontend to manage
    
    return {
        "session_id": session_id,
        "deck_id": payload.deck_id,
        "deck_title": deck.title,
        "deck_owner": db.query(User).filter(User.id == deck.owner_id).first().email,
        "total_cards": len(cards),
        "cards": test_cards,
        "started_at": datetime.now().isoformat(),
        "per_card_seconds": per_card_seconds,
        "time_limit_seconds": time_limit_seconds,
        "ends_at": ends_at.isoformat(),
    }

@router.post("/submit-answer")
def submit_test_answer(
    session_id: str,
    payload: TestAnswerSubmit,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit an answer for a specific card in a test session."""
    # Get the card to check the correct answer
    card = db.query(Card).filter(Card.id == payload.card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    
    # Check if answer is correct (case-insensitive for text answers)
    is_correct = payload.user_answer.strip().lower() == card.answer.strip().lower()
    
    return {
        "card_id": payload.card_id,
        "is_correct": is_correct,
        "correct_answer": card.answer,
        "user_answer": payload.user_answer
    }

@router.post("/complete", response_model=TestSessionResult)
def complete_test_session(
    session_id: str,
    answers: List[TestAnswer],
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Complete a test session and get results."""
    # Parse session_id to get deck info
    try:
        parts = session_id.split("_")
        deck_id = int(parts[1])
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid session ID")
    
    # Get deck info
    deck = db.query(Deck).filter(Deck.id == deck_id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    
    deck_owner = db.query(User).filter(User.id == deck.owner_id).first()
    
    # Calculate results
    total_cards = len(answers)
    correct_answers = sum(1 for answer in answers if answer.is_correct)
    accuracy = (correct_answers / total_cards) * 100 if total_cards > 0 else 0
    total_time = sum(answer.time_taken for answer in answers if answer.time_taken)
    
    # In a real app, you'd save this to a TestSession table
    # For now, return the results
    
    return TestSessionResult(
        session_id=session_id,
        deck_title=deck.title,
        deck_owner=deck_owner.email,
        total_cards=total_cards,
        correct_answers=correct_answers,
        accuracy=round(accuracy, 2),
        total_time=total_time,
        completed_at=datetime.now(),
        answers=answers
    )

@router.get("/stats", response_model=TestStats)
def get_test_stats(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get testing statistics for the current user."""
    # In a real app, you'd query from a TestSession table
    # For now, return mock data showing the concept
    
    return TestStats(
        total_tests_taken=0,  # Would be actual count from database
        total_decks_tested=0,
        average_accuracy=0.0,
        favorite_subjects=[],
        recent_tests=[]
    )

@router.get("/leaderboard")
def get_test_leaderboard(
    deck_id: Optional[int] = None,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get leaderboard for test performance."""
    # In a real app, you'd query test results from database
    # This would show top performers for specific decks or overall
    
    return {
        "message": "Leaderboard feature - would show top test performers",
        "deck_id": deck_id,
        "limit": limit
    }

@router.get("/random-deck")
def get_random_public_deck(
    subject: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get a random public deck for testing."""
    query = db.query(Deck).filter(Deck.visibility == "public")
    
    if subject:
        # Filter by tag/subject
        query = query.filter(Deck.tags.contains(subject))
    
    # Get random deck
    deck = query.order_by(func.random()).first()
    
    if not deck:
        raise HTTPException(status_code=404, detail="No public decks found")
    
    # Get card count
    card_count = db.query(Card).filter(Card.deck_id == deck.id).count()
    
    deck_owner = db.query(User).filter(User.id == deck.owner_id).first()
    
    return {
        "id": deck.id,
        "title": deck.title,
        "description": deck.description,
        "tags": deck.tags,
        "owner": deck_owner.email,
        "card_count": card_count,
        "created_at": deck.created_at
    }
