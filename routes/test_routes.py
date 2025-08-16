from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from datetime import datetime, timedelta
import json
from db import get_db, Deck, Card, User, TestSessionDB
from routes.auth_routes import get_current_user

router = APIRouter(prefix="/tests", tags=["testing"])

# ----- Test Session Models -----

class TestAnswer(BaseModel):
    card_id: int
    user_answer: str
    is_correct: bool
    time_taken: Optional[int] = None  # seconds
    options: Optional[list[str]] = None  # all options for the question

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
    try:
        deck = db.query(Deck).filter(Deck.id == payload.deck_id).first()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    
    # Check if user can access this deck
    if deck.visibility == "private" and deck.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot access private deck")
    
    # Get all cards in the deck
    try:
        cards = db.query(Card).filter(Card.deck_id == payload.deck_id).all()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    if not cards:
        raise HTTPException(status_code=400, detail="Deck has no cards to test")
    import random
    random.shuffle(cards)  # Shuffle questions for random order
    
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
    
    # Store session persistently in DB
    try:
        new_session = TestSessionDB(
            session_id=session_id,
            deck_id=payload.deck_id,
            user_id=current_user.id,
            started_at=datetime.now(),
            completed_at=None,
            total_cards=len(cards),
            correct_answers=None,
            total_time=None,
            answers_json=None
        )
        db.add(new_session)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create test session: {str(e)}")

    return {
        "session_id": session_id,
        "deck_id": payload.deck_id,
        "deck_title": deck.title,
        "deck_owner": db.query(User).filter(User.id == deck.owner_id).first().email,
        "total_cards": len(cards),
        "cards": test_cards,
        "started_at": datetime.now().isoformat(),
    }

def sanitize_string(s):
    if not isinstance(s, str):
        raise HTTPException(status_code=400, detail="Invalid input: string expected")
    s = s.strip()
    if any(ord(c) < 32 for c in s):  # Control chars
        raise HTTPException(status_code=400, detail="Invalid input: control characters not allowed")
    return s

def validate_session_id(session_id: str, db: Session, current_user) -> "TestSessionDB":
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(status_code=400, detail="Invalid session_id")
    session = db.query(TestSessionDB).filter(TestSessionDB.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Session does not belong to current user")
    return session

@router.post("/submit-answer")
def submit_test_answer(
    session_id: str,
    payload: TestAnswerSubmit,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit an answer for a specific card in a test session."""
    # Validate session_id
    validate_session_id(session_id, db, current_user)
    # Validate payload fields
    if not isinstance(payload.card_id, int) or payload.card_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid card_id")
    user_answer = sanitize_string(payload.user_answer)
    if payload.time_taken is not None and (not isinstance(payload.time_taken, int) or payload.time_taken < 0):
        raise HTTPException(status_code=400, detail="Invalid time_taken")
    # Get the card to check the correct answer
    try:
        card = db.query(Card).filter(Card.id == payload.card_id).first()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    # Check if answer is correct (case-insensitive for text answers)
    is_correct = user_answer.lower() == card.answer.strip().lower()
    return {
        "card_id": payload.card_id,
        "is_correct": is_correct,
        "correct_answer": card.answer,
        "user_answer": user_answer
    }

@router.post("/complete", response_model=TestSessionResult)
def complete_test_session(
    session_id: str,
    answers: List[TestAnswer],
    started_at: str,  # New: get started_at from frontend
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Complete a test session and get results, including timing and all options."""
    from dateutil.parser import isoparse
    # Validate session_id and fetch session
    session = validate_session_id(session_id, db, current_user)
    deck_id = session.deck_id
    # Validate started_at
    try:
        started_at_dt = isoparse(sanitize_string(started_at))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid started_at format")
    # Get deck info
    try:
        deck = db.query(Deck).filter(Deck.id == deck_id).first()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    try:
        deck_owner = db.query(User).filter(User.id == deck.owner_id).first()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    # Validate answers
    answer_details = []
    for ans in answers:
        if not isinstance(ans.card_id, int) or ans.card_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid card_id in answers")
        user_answer = sanitize_string(ans.user_answer)
        if not isinstance(ans.is_correct, bool):
            raise HTTPException(status_code=400, detail="Invalid is_correct in answers")
        if ans.time_taken is not None and (not isinstance(ans.time_taken, int) or ans.time_taken < 0):
            raise HTTPException(status_code=400, detail="Invalid time_taken in answers")
        card = db.query(Card).filter(Card.id == ans.card_id).first()
        options = None
        if hasattr(card, 'options_json') and card.options_json:
            try:
                options = json.loads(card.options_json)
            except Exception:
                options = None
        answer_details.append(TestAnswer(
            card_id=ans.card_id,
            user_answer=user_answer,
            is_correct=ans.is_correct,
            time_taken=ans.time_taken,
            options=options
        ))
    # Calculate results
    total_cards = len(answer_details)
    correct_answers = sum(1 for answer in answer_details if answer.is_correct)
    accuracy = (correct_answers / total_cards) * 100 if total_cards > 0 else 0
    completed_at = datetime.now()
    total_time = int((completed_at - started_at_dt).total_seconds())
    # Update the persistent session record in DB
    try:
        test_session = db.query(TestSessionDB).filter(TestSessionDB.session_id == session_id, TestSessionDB.user_id == current_user.id).first()
        if not test_session:
            raise HTTPException(status_code=404, detail="Test session not found")
        test_session.completed_at = completed_at
        test_session.correct_answers = correct_answers
        test_session.total_time = total_time
        test_session.answers_json = json.dumps([ans.dict() for ans in answer_details])
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update test session: {str(e)}")
    return TestSessionResult(
        session_id=session_id,
        deck_title=deck.title,
        deck_owner=deck_owner.email,
        total_cards=total_cards,
        correct_answers=correct_answers,
        accuracy=round(accuracy, 2),
        total_time=total_time,
        completed_at=completed_at,
        answers=answer_details
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
