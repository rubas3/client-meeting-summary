"""UI: Streamlit front end. Run with: streamlit run app.py"""
import datetime

import pandas as pd
import streamlit as st
from streamlit_option_menu import option_menu

import sheets_service as db
import ai_service as ai
import tts_service as tts

st.set_page_config(page_title="Client Meeting App", layout="wide")
st.title("Client Meeting App")

FIELDS = ["f_name", "f_company", "f_contact", "f_email"]


# ---------------- Tab 1: Client Opening ----------------

def submit_client():
    """Runs when 'Add client' is clicked. Form is cleared only if saving succeeds."""
    try:
        new = db.add_client(
            st.session_state.f_name,
            st.session_state.f_company,
            st.session_state.f_contact,
            st.session_state.f_email,
        )
    except ValueError as e:
        st.session_state.msg = ("error", str(e).split("\n"))
    except Exception as e:
        st.session_state.msg = (
            "error",
            [
                "We couldn't save this client right now. Please check your internet "
                "connection and try again in a moment.",
                f"Technical detail: {e}",
            ],
        )
    else:
        st.session_state.msg = ("success", [f"Client {new['client_id']} - {new['name']} added."])
        for key in FIELDS:
            st.session_state[key] = ""


def client_opening_tab():
    # ----- Top: add client form -----
    st.subheader("Open a new client")
    with st.form("client_form"):
        col1, col2 = st.columns(2)
        col1.text_input("Client name *", key="f_name")
        col2.text_input("Company", key="f_company")
        col1.text_input("Contact number * (digits only)", key="f_contact",
                        max_chars=15, placeholder="03001234567")
        col2.text_input("Email *", key="f_email", placeholder="name@company.com")
        st.form_submit_button("Add client", on_click=submit_client)

    msg = st.session_state.pop("msg", None)
    if msg:
        kind, lines = msg
        for line in lines:
            (st.success if kind == "success" else st.error)(line)

    st.divider()

    # ----- Bottom: all clients (MIS) -----
    st.subheader("Clients opened (MIS)")
    try:
        with st.spinner("Fetching clients..."):
            clients = db.get_clients()
    except Exception as e:
        st.error("We couldn't load the client list right now. Please try again in a moment.")
        st.caption(f"Technical detail: {e}")
        return

    if clients:
        st.dataframe(pd.DataFrame(clients), width="stretch", hide_index=True)
    else:
        st.caption("No clients yet.")


# ---------------- Tab 2: Meetings ----------------

def submit_meeting(client_id):
    """Runs when 'Add meeting' is clicked."""
    try:
        db.add_meeting(
            client_id,
            st.session_state.m_date,
            st.session_state.m_agenda,
            st.session_state.m_details,
        )
    except ValueError as e:
        st.session_state.m_msg = ("error", str(e).split("\n"))
    except Exception as e:
        st.session_state.m_msg = (
            "error",
            [
                "We couldn't save this meeting right now. Please check your internet "
                "connection and try again in a moment.",
                f"Technical detail: {e}",
            ],
        )
    else:
        st.session_state.m_msg = ("success", ["Meeting added."])
        st.session_state.m_date = datetime.date.today()
        st.session_state.m_agenda = ""
        st.session_state.m_details = ""


def meetings_tab():
    st.subheader("Select a client")
    try:
        with st.spinner("Fetching clients..."):
            clients = db.get_clients()
    except Exception as e:
        st.error("We couldn't load the client list right now. Please try again in a moment.")
        st.caption(f"Technical detail: {e}")
        return

    if not clients:
        st.info("No clients yet. Add one in the Client Opening tab first.")
        return

    clients_df = pd.DataFrame(clients)
    event = st.dataframe(
        clients_df,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="meetings_client_table",
    )

    selected_rows = event.selection.rows
    if not selected_rows:
        st.caption("Click a row above to select a client.")
        return

    client = clients_df.iloc[selected_rows[0]]
    client_id = client["client_id"]
    st.divider()

    # ----- Top: add meeting form -----
    st.subheader(f"Add meeting - {client['name']} ({client_id})")
    with st.form("meeting_form"):
        st.date_input("Meeting date *", key="m_date")
        st.text_input("Agenda *", key="m_agenda")
        st.text_area("Details *", key="m_details")
        st.form_submit_button("Add meeting", on_click=submit_meeting, args=(client_id,))

    msg = st.session_state.pop("m_msg", None)
    if msg:
        kind, lines = msg
        for line in lines:
            (st.success if kind == "success" else st.error)(line)

    st.divider()

    # ----- Bottom: meeting history for selected client -----
    st.subheader(f"Meeting history - {client['name']}")
    try:
        with st.spinner("Fetching meetings..."):
            history = db.get_meetings(client_id)
    except Exception as e:
        st.error("We couldn't load the meeting history right now. Please try again in a moment.")
        st.caption(f"Technical detail: {e}")
        return

    if history:
        history_df = pd.DataFrame(history).sort_values("date", ascending=False)
        st.table(history_df.set_index("meeting_id"))  # wraps long text instead of cutting it off
    else:
        st.caption("No meetings yet for this client.")



# ---------------- Tab 3: AI Summary ----------------

def summary_tab():
    st.subheader("Select a client")
    try:
        with st.spinner("Fetching clients..."):
            clients = db.get_clients()
            all_meetings = db.get_meetings()
    except Exception as e:
        st.error("We couldn't load client and meeting data right now. Please try again in a moment.")
        st.caption(f"Technical detail: {e}")
        return

    if not clients:
        st.info("No clients yet. Add one in the Client Opening tab first.")
        return

    counts = {}
    for m in all_meetings:
        counts[m["client_id"]] = counts.get(m["client_id"], 0) + 1

    clients_df = pd.DataFrame(clients)
    clients_df["meetings_count"] = clients_df["client_id"].map(counts).fillna(0).astype(int)

    # Only show these columns; meetings_count as text so it left-aligns instead of right-aligning
    display_df = clients_df[["name", "company", "meetings_count"]].copy()
    display_df["meetings_count"] = display_df["meetings_count"].astype(str)

    event = st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="summary_client_table",
    )

    selected_rows = event.selection.rows
    if not selected_rows:
        st.caption("Click a row above to select a client.")
        return

    client = clients_df.iloc[selected_rows[0]]
    client_id = client["client_id"]
    meeting_count = client["meetings_count"]
    st.divider()

    st.subheader(f"AI Summary - {client['name']} ({meeting_count} meeting{'s' if meeting_count != 1 else ''})")

    if meeting_count == 0:
        st.info("This client has no meetings yet, so there is nothing to summarize.")
        return

    if st.button("Generate Summary"):
        try:
            with st.spinner("Generating summary..."):
                history = [m for m in all_meetings if m["client_id"] == client_id]
                st.session_state[f"summary_{client_id}"] = ai.summarize_client(client, history)
                st.session_state.pop(f"audio_{client_id}", None)  # clear any old audio for this client
        except Exception as e:
            st.error("We couldn't generate the summary right now. Please try again in a moment.")
            st.caption(f"Technical detail: {e}")

    summary = st.session_state.get(f"summary_{client_id}")
    if summary:
        st.markdown(summary)

        if st.button("🔊 Listen to Summary"):
            try:
                with st.spinner("Generating audio..."):
                    st.session_state[f"audio_{client_id}"] = tts.text_to_speech(summary)
            except Exception as e:
                st.error("We couldn't generate the audio right now. Please try again in a moment.")
                st.caption(f"Technical detail: {e}")

        audio_bytes = st.session_state.get(f"audio_{client_id}")
        if audio_bytes:
            st.audio(audio_bytes, format="audio/wav")

# ---------------- Sidebar navigation ----------------

with st.sidebar:
    page = option_menu(
        menu_title="Client Meeting App",
        options=["Client Opening", "Meetings", "AI Summary"],
        icons=["person-plus", "calendar-event", "stars"],
        default_index=0,
        key="nav_menu",
    )

if page == "Client Opening":
    client_opening_tab()
elif page == "Meetings":
    meetings_tab()
else:
    summary_tab()