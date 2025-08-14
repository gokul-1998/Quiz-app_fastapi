# Running the program use 
- for UV
```
uv init
uv pip install -r requirements.txt
uv run uvicorn main:app --reload
```
- without uv
```
python3  -m venv env
source env/bin/activate
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

## Features

- Auth: register, login (OAuth2PasswordRequestForm), refresh access token (verifies stored refresh token).
- Decks:
  - CRUD with ownership.
  - Visibility: `public` or `private` (DB-enforced), default `private`.
  - Tags: comma-separated string, used for search/filter.
  - Pagination: `page` and `size`, headers include `X-Total-Count`, `X-Page`, `X-Page-Size`, `X-Total-Pages`.
  - Search: matches deck `title`, `description`, and `tags` simultaneously.
  - Favourites: per-user star/unstar with `favourite` boolean in listing.
  - created_at timestamp on decks.
- Cards:
  - CRUD under a deck.
  - qtype enum: `mcq`, `match`, `fillups`.
  - MCQ requires at least 4 options; stored as JSON.
  - Cards inherit deck visibility (no separate card visibility in API).
- AI (prep): `utils/ai_plan.py` helper for Gemini study plan (endpoint can be added).

## Quick Commands

- Start (uv): `uv run uvicorn main:app --reload`
- Start (venv): `uvicorn main:app --reload`
- Run tests: `uv run pytest -q`

## API Overview (brief)

Auth
- POST `/auth/register`
  - body: `{ "email": str, "password": str }`
  - 200 -> `{ "message": "User registered successfully" }`
- POST `/auth/login`
  - form fields: `username`, `password`
  - 200 -> `{ access_token, refresh_token, token_type: "bearer" }`
- POST `/auth/refresh`
  - header: `Authorization: Bearer <access_token>`
  - body: `{ "refresh_token": str }`
  - 200 -> `{ access_token, token_type: "bearer", refresh_token }`

Decks
- POST `/decks/`
  - body: `{ title, description?, tags?, visibility: "public"|"private" }`
  - 201 -> `DeckOut` (includes `id, owner_id, created_at, card_count, favourite`)
- GET `/decks`
  - query: `search?`, `tag?`, `visibility=public|private|all` (default all), `page` (default 1), `size` (default 10)
  - headers: `X-Total-Count`, `X-Page`, `X-Page-Size`, `X-Total-Pages`
  - 200 -> list of decks (each with `favourite` and `card_count`)
- GET `/decks/{deck_id}`
- PATCH `/decks/{deck_id}` (partial update; no PUT)
- DELETE `/decks/{deck_id}`
- POST `/decks/{deck_id}/favorite` (star)
- DELETE `/decks/{deck_id}/favorite` (unstar)

Cards
- POST `/decks/{deck_id}/cards`
  - For MCQ: `{ qtype: "mcq", question, answer, options: [min 4] }`
  - For others: `{ qtype: "fillups"|"match", question, answer }`
  - 201 -> `CardOut` (no visibility field)
- GET `/decks/{deck_id}/cards`
  - 200 -> list of cards (visible to owner or if deck is public)
- GET `/decks/{deck_id}/cards/{card_id}`
- PATCH `/decks/{deck_id}/cards/{card_id}`
- DELETE `/decks/{deck_id}/cards/{card_id}`

## HTTPie/cURL Examples

Register
```bash
http POST :8000/auth/register email=test@example.com password=Passw0rd!123
```

Login
```bash
http -f POST :8000/auth/login username=test@example.com password=Passw0rd!123
```

Create Deck (public, tags)
```bash
http POST :8000/decks/ \
  Authorization:"Bearer $ACCESS" \
  title="python" description="coding in python" tags="python,programming" visibility="public"
```

Add MCQ Card
```bash
http POST :8000/decks/1/cards Authorization:"Bearer $ACCESS" \
  qtype=mcq question="Capital of France?" answer=Paris \
  options:='["Paris","London","Berlin","Rome"]'
```

List Decks with Search + Pagination
```bash
http GET ':8000/decks?search=python&page=1&size=10' Authorization:"Bearer $ACCESS"
```

Favourite / Unfavourite Deck
```bash
http POST :8000/decks/1/favorite Authorization:"Bearer $ACCESS"
http DELETE :8000/decks/1/favorite Authorization:"Bearer $ACCESS"
```

## Environment

Required (.env)
- `JWT_SECRET`
- `JWT_ALGORITHM` (e.g., HS256)
- `ACCESS_TOKEN_EXPIRE_MINUTES` (default 15)
- `REFRESH_TOKEN_EXPIRE_DAYS` (default 7)

Optional (AI)
- `GOOGLE_API_KEY` (if enabling Gemini features in `utils/ai_plan.py`)

## Notes

- Deck search matches title, description, and tags.
- Cards inherit deck visibility and do not expose a visibility field.
- Some environments may show a bcrypt version warning; upgrading `bcrypt` can silence it.# Quiz_app_frontend
