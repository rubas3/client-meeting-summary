"""Text-to-speech logic: converts an AI summary into spoken audio using Gemini TTS.
No Streamlit code and no Google Sheets code here.

Speed-up: long summaries are split at sentence boundaries into a few chunks, each chunk is
converted in parallel, and the audio is joined back in the original order. The full text is
still read word for word, in the same voice."""
import io
import math
import os
import re
import wave
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()  # reads the .env file in the project folder

TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"  # other prebuilt voices: Puck, Charon, Aoede, Fenrir, ...

# --- Speed settings ---
MIN_CHARS_PER_CHUNK = 350   # texts shorter than this are sent as ONE request (same as before)
MAX_CHUNKS = 4              # at most this many parallel requests (keeps API rate limits in check)
REQUEST_TIMEOUT_MS = 60_000  # give up on one hung request after 60s instead of waiting forever
ATTEMPTS_PER_CHUNK = 2      # the preview model occasionally fails once; try one more time

_client = None


def _get_client():
    """Connect to Gemini once and reuse the connection (same GEMINI_API_KEY as the summary)."""
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is missing. Add it to your .env file.")
        _client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
        )
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


# Splits a long line into sentences. Does NOT split after list numbers like "1." or
# before a lowercase word (e.g. "e.g. the"), so no sentence is ever cut in a bad place.
_SENTENCE_SPLIT = re.compile(r"(?<=[^\d\s][.!?])\s+(?=[A-Z0-9\"'(])")


def _split_into_chunks(text):
    """Split text into a few chunks at line/sentence boundaries, in order.
    No words are dropped or reordered: joining the chunks gives back the same text."""
    n_chunks = min(MAX_CHUNKS, max(1, math.ceil(len(text) / MIN_CHARS_PER_CHUNK)))
    if n_chunks == 1:
        return [text]

    target = math.ceil(len(text) / n_chunks)

    # Break the text into small units: one per line, long lines split into sentences
    units = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) > target:
            units.extend(s.strip() for s in _SENTENCE_SPLIT.split(line) if s.strip())
        else:
            units.append(line)

    # Group units into chunks of roughly equal size
    chunks, current, current_len = [], [], 0
    for unit in units:
        current.append(unit)
        current_len += len(unit)
        if current_len >= target:
            chunks.append("\n".join(current))
            current, current_len = [], 0
    if current:
        chunks.append("\n".join(current))
    return chunks


def _synthesize_chunk(text, config):
    """Convert one chunk of text into raw PCM bytes. Retries once on a temporary failure."""
    last_error = None
    for _ in range(ATTEMPTS_PER_CHUNK):
        try:
            response = _get_client().models.generate_content(
                model=TTS_MODEL,
                contents=text,
                config=config,
            )
            return response.candidates[0].content.parts[0].inline_data.data
        except Exception as e:
            last_error = e
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                break  # quota reached: retrying right away only wastes another request
    raise RuntimeError(f"Could not generate audio: {last_error}")


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

    chunks = _split_into_chunks(spoken_text)
    _get_client()  # create the connection once here, before the worker threads start

    if len(chunks) == 1:
        pcm = _synthesize_chunk(chunks[0], config)
    else:
        with ThreadPoolExecutor(max_workers=min(MAX_CHUNKS, len(chunks))) as pool:
            # map() returns results in the original chunk order, so the audio stays in order
            parts = list(pool.map(lambda c: _synthesize_chunk(c, config), chunks))
        pcm = b"".join(parts)

    return _pcm_to_wav(pcm)