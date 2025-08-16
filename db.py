import os
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, CheckConstraint, UniqueConstraint, DateTime, func
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String)  
    refresh_token = Column(Text, nullable=True)
    decks = relationship("Deck", back_populates="owner", cascade="all, delete-orphan")

class Deck(Base):
    __tablename__ = "decks"
    __table_args__ = (
        CheckConstraint("visibility in ('public','private')", name="ck_decks_visibility"),
    )
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    tags = Column(String, nullable=True)  # Comma-separated tags, e.g. "python,programming"
    visibility = Column(String, nullable=False, default="private")  # public | private
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    owner = relationship("User", back_populates="decks")
    cards = relationship("Card", back_populates="deck", cascade="all, delete-orphan")

class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (
        CheckConstraint("qtype in ('mcq','match','fillups')", name="ck_cards_qtype"),
        CheckConstraint("visibility in ('public','private')", name="ck_cards_visibility"),
    )
    id = Column(Integer, primary_key=True, index=True)
    deck_id = Column(Integer, ForeignKey("decks.id"), index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    qtype = Column(String, nullable=False)
    options_json = Column(Text, nullable=True)  # JSON-encoded options for MCQ
    visibility = Column(String, nullable=False, default="private")
  # public | private

    deck = relationship("Deck", back_populates="cards")


class TestSessionDB(Base):
    __tablename__ = "test_sessions"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True, nullable=False)
    deck_id = Column(Integer, ForeignKey("decks.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    total_cards = Column(Integer, nullable=False)
    correct_answers = Column(Integer, nullable=True)
    total_time = Column(Integer, nullable=True)  # seconds
    answers_json = Column(Text, nullable=True)  # JSON-encoded answers

    user = relationship("User")
    deck = relationship("Deck")

class DeckFavorite(Base):
    __tablename__ = "deck_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "deck_id", name="uq_deck_favorites_user_deck"),
)
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    deck_id = Column(Integer, ForeignKey("decks.id"), nullable=False, index=True)

    user = relationship("User")
    deck = relationship("Deck")


class DeckLike(Base):
    __tablename__ = "deck_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "deck_id", name="uq_deck_likes_user_deck"),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    deck_id = Column(Integer, ForeignKey("decks.id"), nullable=False, index=True)

    user = relationship("User")
    deck = relationship("Deck")

Base.metadata.create_all(bind=engine)

def get_db():  # pragma: no cover
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
