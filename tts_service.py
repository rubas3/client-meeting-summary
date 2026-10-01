"""Text-to-speech logic: converts an AI summary into spoken audio using Speechmatics TTS.
No Streamlit code and no Google Sheets code here.

Speed-up: long summaries are split at sentence boundaries into a few chunks, each chunk is
converted in parallel, and the audio is joined back in the original order. The full text is
still read word for word, in the same voice."""
import io
import math
import os
import re
import struct
import time
import wave
from concurrent.futures import ThreadPoolExecutor

import requests
from dotenv import load_dotenv

load_dotenv()  # reads the .env file in the project folder

TTS_VOICE = "sarah"  # other voices: theo, megan
TTS_URL = f"https://preview.tts.speechmatics.com/generate/{TTS_VOICE}"

REQUEST_TIMEOUT_SECONDS = 60  # give up on a hung request instead of waiting forever
ATTEMPTS = 2                  # the preview service may fail once; try one more time

# --- Speed settings ---
MIN_CHARS_PER_CHUNK = 250   # texts shorter than this are sent as ONE request
MAX_CHUNKS = 4              # at most this many parallel requests (lower it if you see 429 errors)


def _get_api_key():
    """Read the Speechmatics API key from .env."""
    api_key = os.getenv("SPEECHMATICS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("SPEECHMATICS_API_KEY is missing. Add it to your .env file.")
    return api_key


def _clean_for_speech(text):
    """Remove markdown symbols (**, #, bullets) so they are not read aloud."""
    text = re.sub(r"[*#`>]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.MULTILINE)
    return text.strip()


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


def _synthesize_chunk(text, headers, attempts=ATTEMPTS):
    """Convert one chunk of text into WAV bytes. Retries on a temporary failure."""
    last_error = None
    for _ in range(attempts):
        try:
            response = requests.post(
                TTS_URL, headers=headers, json={"text": text}, timeout=REQUEST_TIMEOUT_SECONDS
            )
            if response.status_code == 200:
                return response.content  # already a WAV file (16 kHz)
            last_error = f"{response.status_code} {response.text}"
            if response.status_code in (401, 403, 429):
                break  # bad key or limit reached: retrying right away won't help
        except requests.RequestException as e:
            last_error = e
    raise RuntimeError(f"Could not generate audio: {last_error}")


def _read_wav(wav_bytes):
    """Return (channels, sample_width_bytes, sample_rate, raw_audio) from WAV bytes.
    Reads the header by hand so it also works if the file's length fields are not filled in."""
    if wav_bytes[:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
        raise RuntimeError("Speechmatics returned audio that is not a WAV file.")

    channels, sample_width, sample_rate = 1, 2, 16000
    pos = 12
    while pos + 8 <= len(wav_bytes):
        chunk_id = wav_bytes[pos:pos + 4]
        size = struct.unpack("<I", wav_bytes[pos + 4:pos + 8])[0]
        body = pos + 8
        if chunk_id == b"fmt ":
            _, channels, sample_rate, _, _, bits = struct.unpack("<HHIIHH", wav_bytes[body:body + 16])
            sample_width = bits // 8
        elif chunk_id == b"data":
            end = body + size
            if size == 0 or size == 0xFFFFFFFF or end > len(wav_bytes):
                end = len(wav_bytes)  # length not filled in: take everything that is left
            return channels, sample_width, sample_rate, wav_bytes[body:end]
        pos = body + size + (size & 1)
    raise RuntimeError("Speechmatics returned a WAV file with no audio data.")


def _join_wavs(wav_list):
    """Join several WAV files (same format) into one WAV file, in the given order."""
    channels, sample_width, sample_rate, _ = _read_wav(wav_list[0])
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(sample_width)
        out.setframerate(sample_rate)
        for wav_bytes in wav_list:
            out.writeframes(_read_wav(wav_bytes)[3])
    return buffer.getvalue()


def text_to_speech(text):
    """Convert the given text into WAV audio bytes, ready to play with st.audio(format="audio/wav").
    Raises ValueError if there is no text to speak, RuntimeError on conversion errors."""
    if not text or not text.strip():
        raise ValueError("No summary text to read aloud.")

    spoken_text = _clean_for_speech(text)
    headers = {"Authorization": f"Bearer {_get_api_key()}"}

    start = time.perf_counter()  # start timing
    chunks = _split_into_chunks(spoken_text)

    used_fallback = False
    if len(chunks) == 1:
        audio = _synthesize_chunk(chunks[0], headers)
    else:
        try:
            with ThreadPoolExecutor(max_workers=min(MAX_CHUNKS, len(chunks))) as pool:
                # map() returns results in the original chunk order, so the audio stays in order
                # One try per chunk: if any chunk fails we go straight to the fallback below
                parts = list(pool.map(lambda c: _synthesize_chunk(c, headers, attempts=1), chunks))
            audio = _join_wavs(parts)
        except Exception:
            # Fallback: if any chunk fails (e.g. rate limit), send the whole text in ONE request
            used_fallback = True
            audio = _synthesize_chunk(spoken_text, headers)

    elapsed = time.perf_counter() - start
    mode = "FALLBACK, 1 request" if used_fallback else f"{len(chunks)} chunk(s)"
    print(f"[TTS TIMING] Speechmatics: {elapsed:.2f}s for {len(spoken_text)} characters ({mode})")
    return audio