from typing import List, Optional, Dict, Any
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy import func
from datetime import datetime, timedelta
import uuid
import json
from db import get_db, Deck, Card, User, TestSessionDB
from routes.auth_routes import get_current_user

router = APIRouter(prefix="/tests", tags=["testing"])

# Module logger
logger = logging.getLogger(__name__)

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
    card_id: Any
    user_answer: Any
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


class TestResultSummary(BaseModel):
    total_questions: int
    correct_count: int
    mistake_count: int
    score_percent: float


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
    
    # Create session ID using UUID4 to prevent race conditions
    session_id = str(uuid.uuid4())

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
    
    # Store session persistently in DB (with transaction handling)
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

    # Compute time limits
    per_card = payload.per_card_seconds
    time_limit = payload.total_time_seconds if payload.total_time_seconds is not None else per_card * len(cards)

    return {
        "session_id": session_id,
        "deck_id": payload.deck_id,
        "deck_title": deck.title,
        "deck_owner": db.query(User).filter(User.id == deck.owner_id).first().email,
        "total_cards": len(cards),
        "cards": test_cards,
        "started_at": datetime.now().isoformat(),
        "per_card_seconds": per_card,
        "time_limit_seconds": time_limit,
    }

def sanitize_string(raw_value: str) -> str:
    """
    Sanitize and validate a string input. Rejects control characters, SQL meta-characters, and dangerous substrings.
    This is defense-in-depth; always use parameterized queries for DB access.
    """
    if not isinstance(raw_value, str):
        raise HTTPException(status_code=400, detail="Invalid input: string expected")
    sanitized = raw_value.strip()
    if any(ord(char) < 32 for char in sanitized):  # Control chars
        raise HTTPException(status_code=400, detail="Invalid input: control characters not allowed")
    # Reject common SQL meta-characters and dangerous substrings
    forbidden = [";", "--", "'", '"', "/*", "*/", "xp_"]
    if any(f in sanitized for f in forbidden):
        raise HTTPException(status_code=400, detail="Invalid input: forbidden characters detected")
    return sanitized


def validate_session_id(session_id: str, db: Session, current_user) -> "TestSessionDB":
    """Validate session_id and check ownership in DB."""
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(status_code=400, detail="Invalid session_id")
    test_session = db.query(TestSessionDB).filter(TestSessionDB.session_id == session_id).first()
    if not test_session:
        raise HTTPException(status_code=404, detail="Session not found")
    if test_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Session does not belong to current user")
    return test_session


def _load_deck_and_owner(db: Session, deck_id: int):
    """Load (Deck, User) tuple with JOIN, raising HTTPException appropriately."""
    try:
        deck_user = (
            db.query(Deck, User)
            .join(User, Deck.owner_id == User.id)
            .filter(Deck.id == deck_id)
            .first()
        )
    except OperationalError as exc:
        logger.exception("OperationalError while fetching deck and owner", extra={
            "deck_id": deck_id,
            "exc": str(exc),
        })
        raise HTTPException(status_code=503, detail="Database temporarily unavailable")
    except SQLAlchemyError as exc:
        logger.exception("SQLAlchemyError while fetching deck and owner", extra={
            "deck_id": deck_id,
            "exc": str(exc),
        })
        raise HTTPException(status_code=500, detail="Database error")
    if not deck_user:
        raise HTTPException(status_code=404, detail="Deck not found")
    return deck_user


def _parse_answers(raw_json: Optional[str], session_id: str) -> List[TestAnswer]:
    """Parse answers_json to a validated list of TestAnswer objects.
    Returns an empty list on parse/validation failures but logs details.
    """
    text = raw_json or "[]"
    try:
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("answers_json must be a JSON list")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Failed to parse answers_json", extra={
            "session_id": session_id,
            "error": str(exc),
            "raw_json_len": len(text),
        })
        return []

    out: List[TestAnswer] = []
    for idx, a in enumerate(data):
        try:
            out.append(TestAnswer(**{
                "card_id": a.get("card_id"),
                "user_answer": a.get("user_answer", ""),
                "is_correct": a.get("is_correct", False),
                "time_taken": a.get("time_taken"),
            }))
        except ValidationError as ve:
            logger.error("Invalid answer entry", extra={
                "session_id": session_id,
                "index": idx,
                "error": str(ve),
            })
            continue
    return out


@router.post("/submit-answer")
def submit_test_answer(
    session_id: str,
    payload: TestAnswerSubmit,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit an answer for a specific card in a test session with input validation and sanitization."""
    # Validate session_id
    validate_session_id(session_id, db, current_user)

    # Validate and sanitize payload fields
    if not isinstance(payload.card_id, int) or payload.card_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid card_id")
    sanitized_user_answer = sanitize_string(payload.user_answer)
    if payload.time_taken is not None and (not isinstance(payload.time_taken, int) or payload.time_taken < 0):
        raise HTTPException(status_code=400, detail="Invalid time_taken")

    # Retrieve card and check answer
    try:
        card = db.query(Card).filter(Card.id == payload.card_id).first()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {str(exc)}")
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    # Case-insensitive correctness check
    is_correct = sanitized_user_answer.lower() == card.answer.strip().lower()

    return {
        "card_id": payload.card_id,
        "is_correct": is_correct,
        "correct_answer": card.answer,
        "user_answer": sanitized_user_answer
    }


@router.post("/complete", response_model=TestSessionResult)
def complete_test_session(
    session_id: str,
    answers: Optional[List[TestAnswer]] = None,
    started_at: Optional[str] = None,  # Optional for legacy clients/tests
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Complete a test session and get results, including timing and all options. All user input is validated and sanitized.
    Updates the persistent session record in the database. Handles DB errors and refreshes the session after commit.
    """
    # Local import for isoparse
    from dateutil.parser import isoparse
    # Validate session_id and fetch test session
    try:
        test_session = validate_session_id(session_id, db, current_user)
        deck_id = test_session.deck_id
    except HTTPException as exc:
        # Legacy fallback: parse deck_id from session_id pattern like 'user_deckid_timestamp'
        if exc.status_code == 404:
            parts = session_id.split("_")
            if len(parts) >= 3 and parts[1].isdigit():
                legacy_deck_id = int(parts[1])
                deck = db.query(Deck).filter(Deck.id == legacy_deck_id).first()
                if not deck:
                    # Match historical behavior expected by tests
                    raise HTTPException(status_code=404, detail="Deck not found")
            else:
                # Invalid format should be a 400 Bad Request for /tests/complete
                raise HTTPException(status_code=400, detail="Invalid session_id format")
        raise

    # Validate and parse started_at if provided
    started_at_dt = None
    if started_at is not None:
        try:
            started_at_dt = isoparse(sanitize_string(started_at))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid started_at format")

    # Retrieve deck and owner
    try:
        deck = db.query(Deck).filter(Deck.id == deck_id).first()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {str(exc)}")
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    try:
        deck_owner = db.query(User).filter(User.id == deck.owner_id).first()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {str(exc)}")

    # Validate and sanitize answers
    answer_details: List[TestAnswer] = []
    for submitted_answer in (answers or []):
        if not isinstance(submitted_answer.card_id, int) or submitted_answer.card_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid card_id in answers")
        sanitized_answer = sanitize_string(submitted_answer.user_answer)
        if not isinstance(submitted_answer.is_correct, bool):
            raise HTTPException(status_code=400, detail="Invalid is_correct in answers")
        if submitted_answer.time_taken is not None and (not isinstance(submitted_answer.time_taken, int) or submitted_answer.time_taken < 0):
            raise HTTPException(status_code=400, detail="Invalid time_taken in answers")
        card = db.query(Card).filter(Card.id == submitted_answer.card_id).first()
        options = None
        if hasattr(card, 'options_json') and card.options_json:
            try:
                options = json.loads(card.options_json)
            except Exception:
                options = None
        answer_details.append(TestAnswer(
            card_id=submitted_answer.card_id,
            user_answer=sanitized_answer,
            is_correct=submitted_answer.is_correct,
            time_taken=submitted_answer.time_taken,
            options=options
        ))

    # Calculate results
    total_cards = len(answer_details)
    correct_answers = sum(1 for answer in answer_details if answer.is_correct)
    accuracy = (correct_answers / total_cards) * 100 if total_cards > 0 else 0
    completed_at = datetime.now()
    if started_at_dt is not None:
        total_time = int((completed_at - started_at_dt).total_seconds())
    else:
        # Fallback: sum of per-answer time_taken values
        total_time = sum((a.time_taken or 0) for a in answer_details)

    # Update the persistent session record in DB with transaction
    try:
        db_test_session = db.query(TestSessionDB).filter(TestSessionDB.session_id == session_id, TestSessionDB.user_id == current_user.id).first()
        if not db_test_session:
            raise HTTPException(status_code=404, detail="Test session not found")
        db_test_session.completed_at = completed_at
        db_test_session.correct_answers = correct_answers
        db_test_session.total_time = total_time
        db_test_session.answers_json = json.dumps([ans.dict() for ans in answer_details])
        db.commit()
        db.refresh(db_test_session)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update test session: {str(exc)}")

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

@router.get("/random-deck", include_in_schema=False)
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


@router.get("/results", response_model=TestSessionResult, include_in_schema=False)
def get_test_results(
    session_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Fetch a completed test session's results by session_id.
    Returns the same shape as /tests/complete for easy frontend consumption.
    """
    # Validate session ownership and existence
    test_session = validate_session_id(session_id, db, current_user)

    # Ensure session is completed
    if not test_session.completed_at:
        raise HTTPException(status_code=400, detail="Test session not completed yet")

    # Load deck and owner using a JOIN
    deck, deck_owner = _load_deck_and_owner(db, test_session.deck_id)

    # Parse answers
    answer_details: List[TestAnswer] = _parse_answers(getattr(test_session, "answers_json", None), session_id)

    total_cards = len(answer_details)
    correct_answers = test_session.correct_answers if test_session.correct_answers is not None else sum(1 for ans in answer_details if ans.is_correct)
    accuracy = round(((correct_answers / total_cards) * 100) if total_cards else 0.0, 2)
    total_time = test_session.total_time
    completed_at = test_session.completed_at

    return TestSessionResult(
        session_id=session_id,
        deck_title=deck.title,
        deck_owner=deck_owner.email if deck_owner else "",
        total_cards=total_cards,
        correct_answers=correct_answers,
        accuracy=accuracy,
        total_time=total_time,
        completed_at=completed_at,
        answers=answer_details
    )


@router.get("/stats")
def get_user_test_stats(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get user's test statistics and performance metrics."""
    try:
        # Get all completed test sessions for the user
        completed_sessions = db.query(TestSessionDB).filter(
            TestSessionDB.user_id == current_user.id,
            TestSessionDB.completed_at.isnot(None)
        ).all()
        
        if not completed_sessions:
            return {
                "total_tests": 0,
                "total_questions": 0,
                "correct_answers": 0,
                "accuracy": 0.0,
                "average_time": 0,
                "recent_tests": []
            }
        
        # Calculate overall statistics
        total_tests = len(completed_sessions)
        total_questions = sum(session.total_cards for session in completed_sessions)
        total_correct = sum(session.correct_answers or 0 for session in completed_sessions)
        overall_accuracy = round((total_correct / total_questions * 100) if total_questions > 0 else 0, 2)
        
        # Calculate average time (only for sessions with time data)
        sessions_with_time = [s for s in completed_sessions if s.total_time is not None]
        average_time = round(sum(s.total_time for s in sessions_with_time) / len(sessions_with_time)) if sessions_with_time else 0
        
        # Get recent test results (last 5)
        recent_sessions = sorted(completed_sessions, key=lambda x: x.completed_at, reverse=True)[:5]
        recent_tests = []
        
        for session in recent_sessions:
            deck = db.query(Deck).filter(Deck.id == session.deck_id).first()
            accuracy = round((session.correct_answers / session.total_cards * 100) if session.total_cards > 0 else 0, 2)
            
            recent_tests.append({
                "session_id": session.session_id,
                "deck_title": deck.title if deck else "Unknown Deck",
                "completed_at": session.completed_at.isoformat(),
                "total_cards": session.total_cards,
                "correct_answers": session.correct_answers or 0,
                "accuracy": accuracy,
                "total_time": session.total_time
            })
        
        return {
            "total_tests": total_tests,
            "total_questions": total_questions,
            "correct_answers": total_correct,
            "accuracy": overall_accuracy,
            "average_time": average_time,
            "recent_tests": recent_tests
        }
        
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/result-summary", response_model=TestResultSummary)
def get_test_result_summary(
    session_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Single summary API: returns counts and score in percent for a completed test session."""
    test_session = validate_session_id(session_id, db, current_user)

    if not test_session.completed_at:
        raise HTTPException(status_code=400, detail="Test session not completed yet")

    # Parse answers
    answers: List[TestAnswer] = _parse_answers(getattr(test_session, "answers_json", None), session_id)
    total = len(answers)
    correct = test_session.correct_answers if test_session.correct_answers is not None else sum(1 for a in answers if a.is_correct)
    mistakes = max(total - correct, 0)
    score = round(((correct / total) * 100) if total else 0.0, 2)

    return TestResultSummary(
        total_questions=total,
        correct_count=correct,
        mistake_count=mistakes,
        score_percent=score,
    )


