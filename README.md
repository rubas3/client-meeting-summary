# Client Meeting App

A lightweight Streamlit app to log clients, track meeting history against each one, and generate AI-powered summaries of that history using Google Gemini — all backed by Google Sheets, so no data is lost between sessions.

## Features

- **Client Opening** — add new clients (name, company, contact, email) and view all opened clients in one place.
- **Meetings** — select a client, log meetings (date, agenda, details), and view their full meeting history.
- **AI Summary** — generate a concise, AI-written summary of everything discussed with a client across all their meetings (key decisions, changes over time, open items/next steps) — powered by Google Gemini.
- **Google Sheets persistence** — all client and meeting data is stored in a connected Google Sheet, so it's never lost when the app restarts.

## Tech Stack

- [Streamlit](https://streamlit.io/) — UI
- [gspread](https://github.com/burnash/gspread) — Google Sheets integration
- [Google Gemini API](https://ai.google.dev/) — AI-generated summaries
- Python 3.9+

## Project Structure

```
├── app.py                # Streamlit UI (all 3 tabs)
├── sheets_service.py      # Google Sheets read/write logic
├── ai_service.py          # Gemini prompt building + summary generation
├── requirements.txt       # Python dependencies
└── .env.example            # Environment variable template
```

## Setup

1. **Clone the repo**
   ```
   git clone https://github.com/<your-username>/client-meeting-summary.git
   cd client-meeting-summary
   ```

2. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```

3. **Set up a Google Sheet** with two tabs:
   - `Clients` — header row: `client_id, name, company, contact, email`
   - `Meetings` — header row: `meeting_id, client_id, date, agenda, details`

4. **Create a Google Service Account** (via Google Cloud Console), enable the Google Sheets API and Google Drive API, and download its JSON key as `key.json`. Share your Google Sheet with the service account's email as an **Editor**.

5. **Get a Gemini API key** from [Google AI Studio](https://aistudio.google.com/).

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

## License

This project is provided as-is for internal/client use.
