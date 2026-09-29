"""Text-to-speech logic: converts an AI summary into spoken audio using Gemini TTS.
No Streamlit code and no Google Sheets code here."""
import io
import os
import re
import wave

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()  # reads the .env file in the project folder

TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"  # other prebuilt voices: Puck, Charon, Aoede, Fenrir, ...

_client = None


def _get_client():
    """Connect to Gemini once and reuse the connection (same GEMINI_API_KEY as the summary)."""
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is missing. Add it to your .env file.")
        _client = genai.Client(api_key=api_key)
    return _client


def _clean_for_speech(text):
    """Remove markdown symbols (**, #, bullets) so they are not read aloud."""
    text = re.sub(r"[*#`>]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.MULTILINE)
    return text.strip()


def _pcm_to_wav(pcm_bytes):
    """Gemini returns raw PCM audio (24 kHz, mono, 16-bit). Wrap it as a WAV file."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


def text_to_speech(text):
    """Convert the given text into WAV audio bytes, ready to play with st.audio(format="audio/wav").
    Raises ValueError if there is no text to speak, RuntimeError on conversion errors."""
    if not text or not text.strip():
        raise ValueError("No summary text to read aloud.")

    spoken_text = _clean_for_speech(text)
    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE)
            )
        ),
    )

    last_error = None
    for _ in range(2):  # the preview model occasionally fails once; try one more time
        try:
            response = _get_client().models.generate_content(
                model=TTS_MODEL,
                contents=spoken_text,
                config=config,
            )
            pcm = response.candidates[0].content.parts[0].inline_data.data
            return _pcm_to_wav(pcm)
        except Exception as e:
            last_error = e
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                break  # quota reached: retrying right away only wastes another request
    raise RuntimeError(f"Could not generate audio: {last_error}")