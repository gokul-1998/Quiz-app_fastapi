from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Literal
import os
import google.generativeai as genai

from routes.decks_routes import CardCreateMCQ, CardCreateFillups, CardCreateMatch

router = APIRouter(prefix="/ai", tags=["AI"])

API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise RuntimeError("GOOGLE_API_KEY environment variable not set")
genai.configure(api_key=API_KEY)

class AIGenerateRequest(BaseModel):
    prompt: str = Field(..., example="Explain photosynthesis")
    desired_qtype: Literal["mcq", "fillups", "match"] = Field(..., example="mcq")
    visibility: Literal["public", "private"] = "private"

@router.post("/generate-card", response_model=CardCreateMCQ | CardCreateFillups | CardCreateMatch)
async def generate_card(req: AIGenerateRequest):
    # Call Gemini AI to generate question/answer/options
    # For demo, mock response here

    # TODO: Replace with actual Gemini API call
    if req.desired_qtype == "mcq":
        # Generate MCQ with 4 options
        question = f"What is the answer to: {req.prompt}?"
        answer = "Answer"
        options = ["Answer", "Option1", "Option2", "Option3"]
        return CardCreateMCQ(question=question, answer=answer, qtype="mcq", options=options, visibility=req.visibility)
    elif req.desired_qtype == "fillups":
        question = f"Fill in the blank: {req.prompt}"
        answer = "Answer"
        return CardCreateFillups(question=question, answer=answer, qtype="fillups", visibility=req.visibility)
    else:
        question = f"Match the following: {req.prompt}"
        answer = "Answer"
        return CardCreateMatch(question=question, answer=answer, qtype="match", visibility=req.visibility)


# Summary:
# - Added AI router with a /generate-card endpoint
# - Endpoint accepts prompt, desired_qtype, visibility
# - Returns a CardCreate subtype with generated content
# - Currently mocked, to be replaced with Gemini API call

