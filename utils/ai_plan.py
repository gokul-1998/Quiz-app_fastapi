"""Helper functions to generate personalized study plans using Google Gemini AI."""
from datetime import datetime, timedelta
from typing import List
import google.generativeai as genai

MODEL_NAME = "gemini-2.0-flash"

def setup_gemini(api_key: str):
    """Configure the Gemini SDK and return a GenerativeModel."""
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(MODEL_NAME)

def generate_plan(model, exam_name: str, exam_date: str, strengths: List[str], weaknesses: List[str]) -> str:
    """Return a daily numbered study plan as plain text."""
    prompt = f"""
You are a smart AI tutor. Generate a personalized daily study plan for the exam \"{exam_name}\" scheduled on {exam_date}.

- Focus more on these weak subjects/topics: {', '.join(weaknesses)}
- Spend less time on: {', '.join(strengths)}
- Spread the topics equally till exam day.
- Include one or two specific topics per day.
- Output each day like: \"Day 1 - Maths: Algebra, Physics: Kinematics\"\n\nOnly return the daily breakdown in a numbered list.
    """
    response = model.generate_content(prompt)
    return response.text.strip()
