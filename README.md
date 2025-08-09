# Running the program use 
- for UV
```
uv init
uv pip install -r requirements.txt
uv run uvicorn main:app --reload
```
- without uv
```
pip install -r requirements.txt
uvicorn main:app --reload
```


# fastapi_app

- user can create a deck, and add question and answer to it
- user can take a quiz on the deck
- mcq,match,fill in the blank

## Project Plan

Phase 0 — Setup and Auth (current)
- [x] Separate auth routes into `routes/auth_routes.py` and import in `main.py`.
- [x] JWT-based access/refresh token flow in `auth.py`.
- [x] OAuth2PasswordBearer wired for Swagger Authorize (tokenUrl: `/auth/login`).

Phase 1 — Core Domain: Decks and Cards
- [ ] Models: `Deck`, `Card` (Q/A), with ownership via `User`.
- [ ] CRUD Endpoints:
  - `POST /decks` create deck
  - `GET /decks` list user decks
  - `GET /decks/{deck_id}` get deck
  - `PUT /decks/{deck_id}` update deck
  - `DELETE /decks/{deck_id}` delete deck
  - `POST /decks/{deck_id}/cards` add question/answer
  - `GET /decks/{deck_id}/cards` list cards
- [ ] AuthZ: only owners can mutate their decks/cards.

Phase 2 — Quiz Engine
- [ ] Quiz session endpoints to serve items from a deck.
- [ ] Question types: MCQ, match, fill-in-the-blank.
- [ ] Scoring + simple analytics (accuracy, time, recent performance).

Phase 3 — UX and Docs
- [ ] Add OpenAPI tags and examples for all endpoints.
- [ ] Provide a Postman collection / HTTPie examples.
- [ ] Optional simple frontend or Swagger instructions for flows.

Phase 4 — Persistence and Ops
- [ ] Migrations (e.g., Alembic) and seed scripts.
- [ ] Dockerfile and docker-compose for local dev.
- [ ] Basic CI (lint, type-check, tests).

## Run Locally

1. Set environment variables in `.env`:
   - `JWT_SECRET=your-secret`
   - `JWT_ALGORITHM=HS256`
   - `ACCESS_TOKEN_EXPIRE_MINUTES=15`
   - `REFRESH_TOKEN_EXPIRE_DAYS=7`
2. Install deps: `pip install -r requirements.txt`
3. Start API: `uvicorn main:app --reload`
4. Open Swagger: http://127.0.0.1:8000/docs (Authorize with `/auth/login`).