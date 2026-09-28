"""AI logic: builds the prompt and calls Gemini to summarize a client's meetings.
No Streamlit code and no Google Sheets code here."""
import os

from dotenv import load_dotenv
from google import genai

load_dotenv()  # reads the .env file in the project folder

GEMINI_MODEL = "gemini-2.5-flash"

_client = None


def _get_client():
    """Connect to Gemini once and reuse the connection."""
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is missing. Add it to your .env file.")
        _client = genai.Client(api_key=api_key)
    return _client


def _build_prompt(client, meetings):
    """Turn the client's meeting history into one prompt for Gemini."""
    meetings_sorted = sorted(meetings, key=lambda m: m["date"])
    history_text = "\n\n".join(
        f"Date: {m['date']}\nAgenda: {m['agenda']}\nDetails: {m['details']}"
        for m in meetings_sorted
    )

    return (
        f"You are summarizing meeting history for a client named {client['name']}"
        f"{' from ' + client['company'] if client.get('company') else ''}.\n\n"
        "Below is the full meeting history, oldest first. Write a short, clear summary with:\n"
        "1. What has been discussed so far (overall)\n"
        "2. Key decisions or agreements made, and the final/current status of each\n"
        "3. Any changes or revisions made over time (e.g. scope, budget, timeline, or design "
        "changes) - mention what it changed from and to, only if the meetings show a change\n"
        "4. Open items / next steps\n\n"
        "Important rules:\n"
        "- Use ONLY the information in the meeting details below. Do not add, assume, or infer "
        "any fact, name, number, or decision that is not explicitly stated.\n"
        "- If something is unclear, ambiguous, or not mentioned, say so or leave it out - never guess.\n"
        "- Do not repeat the raw meeting log back; write an actual summary.\n"
        "- Keep it concise and easy to scan.\n\n"
        "Meeting history:\n"
        f"{history_text}"
    )


def summarize_client(client, meetings):
    """Return an AI-generated summary of a client's meeting history.
    Raises ValueError if there is nothing to summarize, RuntimeError/Exception on API errors."""
    if not meetings:
        raise ValueError("No meetings to summarize for this client yet.")

    prompt = _build_prompt(client, meetings)
    response = _get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={"temperature": 0.2},  # lower = sticks closer to the given facts, less creative guessing
    )
    return response.text