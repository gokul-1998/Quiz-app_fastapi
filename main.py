import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from routes.auth_routes import router as auth_router
from routes.decks_routes import router as decks_router
from routes.ai_routes import router as ai_router
from routes.test_routes import router as test_router
from routes.dashboard_routes import router as dashboard_router

load_dotenv()

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(decks_router)
app.include_router(ai_router)
app.include_router(test_router)
app.include_router(dashboard_router)
