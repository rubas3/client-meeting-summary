# Client Meeting App

A lightweight Streamlit app to log clients, track meeting history against each one, generate AI-powered summaries of that history using Google Gemini, and listen to the summary read aloud. All data is stored in Google Sheets, so nothing is lost between sessions.

## Features

- **Client Opening** — add new clients (name, company, contact, email) and view all opened clients in one place.
- **Meetings** — select a client, log meetings (date, agenda, details), and view their full meeting history.
- **AI Summary** — generate a concise, AI-written summary of everything discussed with a client across all their meetings (key decisions, changes over time, open items/next steps), powered by Google Gemini.
- **Listen to Summary** — hear the generated summary read aloud in a natural voice (Gemini text-to-speech). Long summaries are converted in parallel chunks to keep the wait short.
- **Google Sheets persistence** — all client and meeting data is stored in a connected Google Sheet, so it's never lost when the app restarts.

## Tech Stack

- [Streamlit](https://streamlit.io/) — UI
- [gspread](https://github.com/burnash/gspread) — Google Sheets integration
- [Google Gemini API](https://ai.google.dev/) — AI summaries and text-to-speech audio
- Python 3.10+

## Project Structure

```
├── app.py                 # Streamlit UI (all 3 tabs)
├── sheets_service.py      # Google Sheets read/write logic
├── ai_service.py          # Gemini prompt building + summary generation
├── tts_service.py         # Gemini text-to-speech (audio for the summary)
├── requirements.txt       # Python dependencies
├── .env.example           # Environment variable template
└── .gitignore             # Keeps .env and key.json out of Git
```

## Setup

1. **Clone the repo**
 
2. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```

3. **Set up a Google Sheet** with two tabs (names and headers must match exactly):
   - `Clients` — header row: `client_id, name, company, contact, email`
   - `Meetings` — header row: `meeting_id, client_id, date, agenda, details`

4. **Create a Google Service Account** (via Google Cloud Console), enable the Google Sheets API and Google Drive API, and download its JSON key as `key.json`. Share your Google Sheet with the service account's email as an **Editor**.

5. **Get a Gemini API key** from [Google AI Studio](https://aistudio.google.com/). The same key is used for summaries and audio.

6. **Configure environment variables** — copy `.env.example` to `.env` and fill in:
   ```
   GEMINI_API_KEY=your_gemini_api_key_here
   SHEET_ID=your_google_sheet_id_here
   KEY_FILE=key.json
   ```

7. **Run the app**
   ```
   streamlit run app.py
   ```

> **Keep `.env` and `key.json` private.** They contain secrets and are listed in `.gitignore`. Never commit or share them.

For a detailed, click-by-click walkthrough, see the *Client Meeting App – Setup & Configuration Guide*.

## Notes & Troubleshooting

- **"High demand" (503) or rate-limit (429) messages** come from Google's Gemini service and are usually temporary. The summary step retries automatically; if it still fails, wait a moment and click again. On the free Gemini tier, audio may occasionally hit rate limits, so wait a minute and retry.
- **Audio time:** generation takes a few seconds and grows with summary length.
- **Streamlit errors about `width` / `use_container_width`:** upgrade Streamlit with `pip install -U streamlit`.
- **Cloud deployment (optional):** if a `key.json` file can't be uploaded (e.g. Streamlit Cloud), put the full contents of the service account JSON in a `GCP_SERVICE_ACCOUNT_JSON` secret/environment variable and the app will create the key file automatically.

## License

This project is provided as-is for internal/client use.