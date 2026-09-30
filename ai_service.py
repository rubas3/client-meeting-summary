"""AI logic: builds the prompt and calls Gemini to summarize a client's meetings.
No Streamlit code and no Google Sheets code here."""
import os
import time

from dotenv import load_dotenv
from google import genai

load_dotenv()  # reads the .env file in the project folder

GEMINI_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-2.5-flash-lite"  # used only if the main model stays overloaded

RETRIES_PER_MODEL = 3        # tries per model when Google is temporarily overloaded
RETRY_WAIT_SECONDS = (2, 4)  # wait before the 2nd and 3rd try (short, so the user isn't kept waiting long)

# Temporary problems on Google's side: worth trying again
_TEMPORARY_ERRORS = ("503", "UNAVAILABLE", "500", "INTERNAL", "504", "DEADLINE_EXCEEDED")
# Quota used up: retrying the same model right away is pointless, but another model has its own quota
_QUOTA_ERRORS = ("429", "RESOURCE_EXHAUSTED")

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


def _generate_with_retry(model, prompt):
    """Call one model. Retries a few times if Google is temporarily overloaded (503 etc.).
    Any other error (or a quota error) is raised straight away."""
    for attempt in range(RETRIES_PER_MODEL):
        try:
            response = _get_client().models.generate_content(
                model=model,
                contents=prompt,
                config={"temperature": 0.2},  # lower = sticks closer to the given facts, less creative guessing
            )
            return response.text
        except Exception as e:
            message = str(e)
            is_temporary = any(code in message for code in _TEMPORARY_ERRORS)
            is_last_attempt = attempt == RETRIES_PER_MODEL - 1
            if not is_temporary or is_last_attempt:
                raise
            time.sleep(RETRY_WAIT_SECONDS[min(attempt, len(RETRY_WAIT_SECONDS) - 1)])


def summarize_client(client, meetings):
    """Return an AI-generated summary of a client's meeting history.
    Raises ValueError if there is nothing to summarize, RuntimeError/Exception on API errors."""
    if not meetings:
        raise ValueError("No meetings to summarize for this client yet.")

    prompt = _build_prompt(client, meetings)

    try:
        return _generate_with_retry(GEMINI_MODEL, prompt)
    except Exception as e:
        message = str(e)
        can_fall_back = any(code in message for code in _TEMPORARY_ERRORS + _QUOTA_ERRORS)
        if not can_fall_back or not FALLBACK_MODEL or FALLBACK_MODEL == GEMINI_MODEL:
            raise
        # Main model is overloaded or out of quota: try the backup model once (with the same retries)
        return _generate_with_retry(FALLBACK_MODEL, prompt)