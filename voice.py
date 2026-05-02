"""
voice.py – Transcribes an audio file and extracts expense details using Whisper.

Supported input formats (file upload AND live browser MediaRecorder):
    WAV, MP3, M4A, OGG, WEBM, FLAC, AAC

Browser MediaRecorder typically outputs audio/webm or audio/ogg.
Whisper works best with WAV — this module converts any format to WAV
automatically using pydub (which wraps ffmpeg under the hood).
"""

import re
import logging
from pathlib import Path
from typing import TypedDict, Optional

logger = logging.getLogger(__name__)

# ── Supported input MIME types ────────────────────────────────────────────────
SUPPORTED_MIME_TYPES = {
    "audio/wav",  "audio/wave",   "audio/x-wav",
    "audio/mpeg", "audio/mp3",
    "audio/mp4",  "audio/m4a",    "audio/x-m4a",
    "audio/ogg",  "audio/opus",
    "audio/webm", "audio/webm;codecs=opus",
    "audio/flac", "audio/aac",
    "application/octet-stream",     # some browsers send this as fallback
}

# File extension → pydub format string
EXTENSION_FORMAT_MAP = {
    ".wav":  "wav",
    ".mp3":  "mp3",
    ".m4a":  "m4a",
    ".mp4":  "mp4",
    ".ogg":  "ogg",
    ".opus": "ogg",
    ".webm": "webm",
    ".flac": "flac",
    ".aac":  "aac",
}

# Words that carry no expense meaning
IGNORE_WORDS = frozenset({
    "for", "rupees", "rs", "bought", "buy", "purchase", "paid", "i",
    "the", "a", "an", "spent", "on", "and", "some", "of", "worth",
    "total", "cost", "price", "amount",
})

# Maps spoken words to digit values
WORD_TO_NUMBER = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
}


class VoiceExpenseResult(TypedDict):
    transcript:    str
    item:          Optional[str]
    amount:        Optional[float]
    source_format: str          # e.g. "webm" — useful for debugging


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def process_voice_expense(audio_path: str) -> VoiceExpenseResult:
    """
    Transcribe any supported audio file and extract item + amount.

    Automatically converts non-WAV formats (webm, ogg, mp3…) to WAV
    before passing to Whisper.

    Args:
        audio_path: Path to the saved audio file (any supported format).

    Returns:
        VoiceExpenseResult with transcript, item, amount, and source_format.
    """
    path = Path(audio_path)
    if not path.exists():
        logger.error("Audio file not found: %s", audio_path)
        return _empty_result("unknown")

    source_format = path.suffix.lower().lstrip(".")
    logger.info("Processing audio: %s  format=%s  size=%d bytes",
                path.name, source_format, path.stat().st_size)

    # ── Step 1: Convert to WAV if needed ──────────────────────────────────────
    wav_path = _ensure_wav(path)
    if wav_path is None:
        return _empty_result(source_format)

    # ── Step 2: Transcribe with Whisper ───────────────────────────────────────
    transcript = _transcribe(wav_path)

    # ── Step 3: Clean up converted temp file ──────────────────────────────────
    if wav_path != path and wav_path.exists():
        wav_path.unlink(missing_ok=True)
        logger.debug("Removed temp WAV: %s", wav_path.name)

    if not transcript:
        return _empty_result(source_format)

    # ── Step 4: Extract structured data ───────────────────────────────────────
    text_lower = transcript.lower()
    item   = _extract_item(text_lower)
    amount = _extract_amount(text_lower)

    logger.info("Voice result — item: %s  amount: %s", item, amount)

    return VoiceExpenseResult(
        transcript=transcript,
        item=item,
        amount=amount,
        source_format=source_format,
    )


def is_supported_audio(content_type: str) -> bool:
    """Return True if the MIME type is a known audio format."""
    ct = content_type.lower().split(";")[0].strip()
    return ct in SUPPORTED_MIME_TYPES or ct.startswith("audio/")


# ══════════════════════════════════════════════════════════════════════════════
# FORMAT CONVERSION
# ══════════════════════════════════════════════════════════════════════════════

def _ensure_wav(path: Path) -> Optional[Path]:
    """
    Return a WAV path suitable for Whisper.
      - Already WAV  → return as-is
      - Other format → convert via pydub (requires ffmpeg) → return temp WAV
      - Conversion fails → return original path and let Whisper try directly
    """
    suffix = path.suffix.lower()

    if suffix == ".wav":
        return path

    # Try pydub conversion
    try:
        from pydub import AudioSegment
    except ImportError:
        logger.warning(
            "pydub not installed — skipping conversion of %s. "
            "Install with:  pip install pydub  "
            "and ffmpeg:    https://ffmpeg.org/download.html",
            suffix,
        )
        return path   # Whisper can handle mp3 / m4a natively

    fmt = EXTENSION_FORMAT_MAP.get(suffix)
    if not fmt:
        logger.warning("Unknown extension %s — passing raw file to Whisper", suffix)
        return path

    wav_path = path.with_suffix(".converted.wav")

    try:
        logger.info("Converting %s → WAV (16 kHz mono) via pydub", suffix)
        audio = AudioSegment.from_file(str(path), format=fmt)
        audio = audio.set_frame_rate(16_000).set_channels(1)  # Whisper prefers 16 kHz mono
        audio.export(str(wav_path), format="wav")
        logger.info("Conversion done → %s  (%d bytes)", wav_path.name, wav_path.stat().st_size)
        return wav_path

    except Exception as exc:
        logger.exception("pydub conversion failed for %s: %s — passing raw to Whisper", path.name, exc)
        return path


# ══════════════════════════════════════════════════════════════════════════════
# TRANSCRIPTION
# ══════════════════════════════════════════════════════════════════════════════

def _transcribe(audio_path: Path) -> Optional[str]:
    """Run Whisper on the audio file and return the transcript string."""
    try:
        import whisper
    except ImportError:
        logger.error("openai-whisper not installed. Run: pip install openai-whisper")
        return None

    try:
        logger.info("Loading Whisper base model…")
        model  = whisper.load_model("base")
        result = model.transcribe(
            str(audio_path),
            language="en",      # force English — faster and more accurate for short clips
            task="transcribe",
            fp16=False,         # CPU-safe (no GPU required)
        )
        text = result.get("text", "").strip()
        logger.info("Whisper transcript: %s", text)
        return text or None

    except Exception as exc:
        logger.exception("Whisper transcription failed: %s", exc)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# AMOUNT EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def _extract_amount(text: str) -> Optional[float]:
    """
    Extract a numeric amount from transcribed text.
    Handles digit strings ("500", "1,200") and spoken numbers ("five hundred").
    """
    # Priority 1: digit-based
    for raw in re.findall(r"\b\d[\d,]*(?:\.\d{1,2})?\b", text):
        try:
            value = float(raw.replace(",", ""))
            if 1 <= value <= 1_000_000:
                return value
        except ValueError:
            continue

    # Priority 2: word-based ("two hundred fifty")
    total   = 0
    current = 0
    for word in text.split():
        word = word.strip(".,!?")
        if word not in WORD_TO_NUMBER:
            continue
        num = WORD_TO_NUMBER[word]
        if num == 1000:
            total  += (current or 1) * 1000
            current = 0
        elif num == 100:
            current = (current or 1) * 100
        else:
            current += num

    total += current
    return float(total) if total > 0 else None


# ══════════════════════════════════════════════════════════════════════════════
# ITEM EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def _extract_item(text: str) -> str:
    """
    Extract the most likely item name from transcribed text.
    Filters filler words, digits, and very short tokens.
    """
    words      = re.findall(r"[a-z]+", text)
    candidates = [w for w in words if w not in IGNORE_WORDS and len(w) > 2]
    return candidates[0].capitalize() if candidates else "Unknown"


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _empty_result(source_format: str) -> VoiceExpenseResult:
    return VoiceExpenseResult(
        transcript="",
        item=None,
        amount=None,
        source_format=source_format,
    )
