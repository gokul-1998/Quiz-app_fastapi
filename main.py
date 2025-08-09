import os
from fastapi import FastAPI
from dotenv import load_dotenv
from routes.auth_routes import router as auth_router
from routes.decks_routes import router as decks_router
from routes.ai_routes import router as ai_router

load_dotenv()

app = FastAPI()

app.include_router(auth_router)
app.include_router(decks_router)
app.include_router(ai_router)
