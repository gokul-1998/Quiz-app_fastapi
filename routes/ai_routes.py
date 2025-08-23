from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Literal
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

from routes.decks_routes import CardCreateMCQ, CardCreateFillups, CardCreateMatch

class AIQuestion(BaseModel):
    question: str
    answer: str
    qtype: Literal["mcq", "fillups", "match"]
    options: list[str] | None = None

router = APIRouter(prefix="/ai", tags=["AI"])

class AIGenerateRequest(BaseModel):
    prompt: str = Field(..., example="Explain photosynthesis")
    desired_qtype: Literal["mcq", "fillups", "match"] = Field(..., example="mcq")
    count: int = Field(1, gt=0, le=20, example=5)


def _generate_with_gemini(prompt: str, qtype: str) -> tuple[str, str, list[str] | None]:
    """Generate question, answer, and options (if MCQ) using Gemini 2.0 Flash."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        # Runtime guard to make function testable without import-time failure
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY not set")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    if qtype == "mcq":
        prompt_text = f"""Generate an educational multiple-choice question with 4 options about: {prompt}
        
        Format your response as a JSON object with these exact keys:
        {{
            "question": "The question text",
            "answer": "The correct answer (must match one of the options exactly)",
            "options": ["Option 1", "Option 2 (correct)", "Option 3", "Option 4"]
        }}"""
    elif qtype == "fillups":
        prompt_text = f"""Generate a fill-in-the-blank question about: {prompt}
        
        Format your response as a JSON object with these exact keys:
        {{
            "question": "The question with a blank like ____",
            "answer": "The exact text that fills the blank",
            "options": null
        }}"""
    else:  # match
        prompt_text = f"""Generate a matching question (pairs to match) about: {prompt}
        
        Format your response as a JSON object with these exact keys:
        {{
            "question": "The matching prompt (e.g., 'Match the following terms to their definitions')",
            "answer": "The correct matching (e.g., 'A-1, B-3, C-2')",
            "options": null
        }}"""

    try:
        response = model.generate_content(prompt_text)
        import json, re
        raw = response.text.strip()
        # Attempt to extract first JSON block if model wraps it in markdown
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            raw_json = match.group(0)
        else:
            raw_json = raw
        try:
            result = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Gemini did not return valid JSON: {raw[:200]}"
            )
        return result["question"], result["answer"], result.get("options")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate content: {str(e)}"
        )

from fastapi import Body
from typing import List

@router.post("/generate-card", response_model=List[AIQuestion])
async def generate_card(req: AIGenerateRequest = Body(...)):
    """Generate one or more flashcards using Gemini AI based on the given prompt and question type."""
    try:
        seen = set()
        cards = []
        attempts = 0
        max_attempts = req.count * 3  # Avoid infinite loops if model repeats
        while len(cards) < req.count and attempts < max_attempts:
            question, answer, options = _generate_with_gemini(req.prompt, req.desired_qtype)
            key = (question.strip().lower(), answer.strip().lower())
            if key not in seen:
                seen.add(key)
                if req.desired_qtype == "mcq":
                    if not options or len(options) < 4:
                        continue  # skip invalid MCQ
                    cards.append(AIQuestion(question=question, answer=answer, qtype="mcq", options=options))
                elif req.desired_qtype == "fillups":
                    cards.append(AIQuestion(question=question, answer=answer, qtype="fillups"))
                else:  # match
                    cards.append(AIQuestion(question=question, answer=answer, qtype="match"))
            attempts += 1
        if not cards:
            raise HTTPException(status_code=500, detail="Failed to generate any unique cards.")
        return cards
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating card(s): {str(e)}"
        )


# Summary:
# - Added AI router with a /generate-card endpoint
# - Endpoint accepts prompt, desired_qtype, visibility
# - Returns a CardCreate subtype with generated content
# - Currently mocked, to be replaced with Gemini API call

