"""Backend: all Google Sheets logic for clients. No UI code here."""
import os
import re

import gspread
from dotenv import load_dotenv

load_dotenv()  # reads the .env file in the project folder

CLIENT_HEADERS = ["client_id", "name", "company", "contact", "email"]

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"\d{10,15}", re.ASCII)  # digits only, 10-15 long

_ws = None  # Clients worksheet: connected once, reused. Data itself is NOT cached.


def _get_clients_ws():
    """Connect straight to the Clients tab using values from .env (once)."""
    global _ws
    if _ws is None:
        sheet_id = os.getenv("SHEET_ID", "").strip()
        key_file = os.getenv("KEY_FILE", "key.json").strip()
        if not sheet_id:
            raise RuntimeError("SHEET_ID is missing. Add it to your .env file.")
        if not os.path.exists(key_file):
            raise RuntimeError(f"Service account key file not found: {key_file}")
        gc = gspread.service_account(filename=key_file)
        _ws = gc.open_by_key(sheet_id).worksheet("Clients")
    return _ws


def get_clients():
    """Return all clients as a list of dicts (every value stays as text).
    Always reads fresh from the sheet, so changes show up immediately."""
    rows = _get_clients_ws().get_all_values()
    if len(rows) < 2:
        return []
    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:] if any(row)]


def validate_client(name, contact, email):
    """Return a list of error messages (empty list = valid)."""
    errors = []
    if not name.strip():
        errors.append("Client name is required.")
    if not contact.strip():
        errors.append("Contact number is required.")
    elif not PHONE_PATTERN.fullmatch(contact.strip()):
        errors.append("Contact number must contain digits only (10 to 15 digits), e.g. 03001234567.")
    if not email.strip():
        errors.append("Email is required.")
    elif not EMAIL_PATTERN.fullmatch(email.strip()):
        errors.append("Email format is invalid, e.g. name@company.com.")
    return errors


def _next_client_id(existing_ids):
    """C001, C002, ... based on the highest existing number."""
    numbers = [int(i[1:]) for i in existing_ids if i.startswith("C") and i[1:].isdigit()]
    return f"C{(max(numbers) if numbers else 0) + 1:03d}"


def _find_duplicate_client(existing_clients, contact, email):
    """Return the existing client dict that matches this email or contact number, or None.
    Comparison is case-insensitive for email and ignores nothing for contact (digits only already)."""
    email_norm = email.strip().lower()
    contact_norm = contact.strip()
    for c in existing_clients:
        if email_norm and c.get("email", "").strip().lower() == email_norm:
            return c
        if contact_norm and c.get("contact", "").strip() == contact_norm:
            return c
    return None


def add_client(name, company="", contact="", email=""):
    """Validate, save a new client to the sheet, and return its data.
    Raises ValueError (messages separated by newlines) if validation fails,
    including if a client with the same email or contact number already exists."""
    errors = validate_client(name, contact, email)
    if errors:
        raise ValueError("\n".join(errors))

    existing_clients = get_clients()
    duplicate = _find_duplicate_client(existing_clients, contact, email)
    if duplicate:
        raise ValueError(
            f"A client with this email or contact number already exists: "
            f"{duplicate.get('client_id', '')} - {duplicate.get('name', '')}."
        )

    ws = _get_clients_ws()
    client_id = _next_client_id(ws.col_values(1)[1:])  # fresh read of column A only
    row = [client_id, name.strip(), company.strip(), contact.strip(), email.strip().lower()]
    # RAW keeps values as typed (phone numbers keep their leading 0)
    ws.append_row(row, value_input_option="RAW")
    return dict(zip(CLIENT_HEADERS, row))


# ---------------- Meetings ----------------

MEETING_HEADERS = ["meeting_id", "client_id", "date", "agenda", "details"]

_meetings_ws = None


def _get_meetings_ws():
    """Connect to the Meetings tab once and reuse the connection."""
    global _meetings_ws
    if _meetings_ws is None:
        sheet_id = os.getenv("SHEET_ID", "").strip()
        key_file = os.getenv("KEY_FILE", "key.json").strip()
        if not sheet_id:
            raise RuntimeError("SHEET_ID is missing. Add it to your .env file.")
        gc = gspread.service_account(filename=key_file)
        _meetings_ws = gc.open_by_key(sheet_id).worksheet("Meetings")
    return _meetings_ws


def get_meetings(client_id=None):
    """Return meetings as a list of dicts. If client_id is given, only that client's meetings."""
    rows = _get_meetings_ws().get_all_values()
    if len(rows) < 2:
        return []
    headers = rows[0]
    meetings = [dict(zip(headers, row)) for row in rows[1:] if any(row)]
    if client_id is not None:
        meetings = [m for m in meetings if m["client_id"] == client_id]
    return meetings


def validate_meeting(agenda, meeting_date, details):
    """Return a list of error messages (empty list = valid)."""
    errors = []
    if not agenda.strip():
        errors.append("Agenda is required.")
    if not meeting_date:
        errors.append("Meeting date is required.")
    if not details.strip():
        errors.append("Meeting details are required, so the AI summary has actual content to work from.")
    return errors


def _next_meeting_id(existing_ids):
    """M0001, M0002, ... based on the highest existing number."""
    numbers = [int(i[1:]) for i in existing_ids if i.startswith("M") and i[1:].isdigit()]
    return f"M{(max(numbers) if numbers else 0) + 1:04d}"


def add_meeting(client_id, meeting_date, agenda, details=""):
    """Validate, save a new meeting to the sheet, and return its data.
    Raises ValueError if validation fails."""
    errors = validate_meeting(agenda, meeting_date, details)
    if errors:
        raise ValueError("\n".join(errors))

    ws = _get_meetings_ws()
    meeting_id = _next_meeting_id(ws.col_values(1)[1:])  # fresh read of column A only
    row = [meeting_id, client_id, str(meeting_date), agenda.strip(), details.strip()]
    ws.append_row(row, value_input_option="RAW")
    return dict(zip(MEETING_HEADERS, row))