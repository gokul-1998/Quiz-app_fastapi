import os
from fastapi import FastAPI
from dotenv import load_dotenv
from routes.auth_routes import router as auth_router

load_dotenv()

app = FastAPI()

app.include_router(auth_router)
