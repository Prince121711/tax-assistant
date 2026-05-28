"""

ocr_engine.py

─────────────────────────────────────────────────────────────────────────────

OCR Engine for Tamil + English bills (crumpled, printed, GST invoices)

Supports:

  • Local shop estimates (அபிநயா புரவிசன்ஸ style)

  • Formal GST tax invoices (Bharathi Agencies, Mythili Sales etc.)

  • Mixed Tamil + English text

  • Wrinkled / crumpled paper

  • Handwritten annotations



Pipeline:

  1. Image preprocessing  → OpenCV (denoise, deskew, binarize, sharpen)

  2. OCR                  → PaddleOCR text extraction

  3. Structured extraction→ Gemini Vision API (items, amounts, GST, vendor)

  4. Post-processing      → Clean & validate numbers

─────────────────────────────────────────────────────────────────────────────

Install:

    pip install paddleocr paddlepaddle opencv-python pillow numpy requests

"""



import os, re, json, base64, logging, traceback, time, importlib

from pathlib import Path

from typing   import Optional

from dotenv import load_dotenv


# Configure logging early so module-level code can log safely.
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ocr_engine")

# Load environment variables from api.env
load_dotenv("api.env")


import cv2

import numpy as np

from PIL import Image
import pytesseract

# ── Tesseract binary path ────────────────────────────────────────────────────
# Priority:  TESSERACT_CMD env var  →  Windows Program Files  →  Linux /usr/bin
import shutil as _shutil
_TESS_CMD = (
    os.environ.get("TESSERACT_CMD")
    or _shutil.which("tesseract")                        # found on PATH (any OS)
    or r"C:\Program Files\Tesseract-OCR\tesseract.exe"  # Windows default install
    or "/usr/bin/tesseract"                              # Linux fallback
)
pytesseract.pytesseract.tesseract_cmd = _TESS_CMD
log.info("Tesseract path: %s", _TESS_CMD)



# Import cache manager for rate limiting & caching

from api_cache_manager import (

    init_cache_manager, get_cache, get_queue, get_retry_config, get_quality_tracker

)






# Initialize cache manager on module load

init_cache_manager(cache_dir="./api_cache", max_requests_per_minute=10)





# ═══════════════════════════════════════════════════════════════════════════════

# STEP 1 — IMAGE PREPROCESSING

# ═══════════════════════════════════════════════════════════════════════════════



def preprocess_image(image_path: str) -> np.ndarray:

    """

    Clean a crumpled / wrinkled bill image for best OCR accuracy.

    Returns a cleaned BGR numpy array.

    """

    log.info(f"Preprocessing: {image_path}")

    img = cv2.imread(image_path)

    if img is None:

        raise FileNotFoundError(f"Cannot read image: {image_path}")



    original_h, original_w = img.shape[:2]



    # ── 1. Upscale small images (receipts often photographed from far) ─────────

    if max(original_h, original_w) < 1500:

        scale = 1500 / max(original_h, original_w)

        img   = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        log.info(f"  Upscaled {original_w}x{original_h} → {img.shape[1]}x{img.shape[0]}")



    # ── 2. Convert to grayscale ────────────────────────────────────────────────

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)



    # ── 3. Deskew (fix tilted receipts) ───────────────────────────────────────

    gray = _deskew(gray)



    # ── 4. Denoise (salt-and-pepper from crumpled paper) ──────────────────────

    denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)



    # ── 5. Adaptive binarization (handles uneven lighting on crumpled paper) ───

    binary = cv2.adaptiveThreshold(

        denoised, 255,

        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,

        cv2.THRESH_BINARY,

        blockSize=31,   # larger block handles shadows from wrinkles

        C=12

    )



    # ── 6. Sharpen (enhance thin Tamil characters) ─────────────────────────────

    kernel  = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])

    sharpened = cv2.filter2D(binary, -1, kernel)



    # ── 7. Morphological cleanup (close small gaps in characters) ─────────────

    kernel2   = np.ones((2, 2), np.uint8)

    cleaned   = cv2.morphologyEx(sharpened, cv2.MORPH_CLOSE, kernel2)



    # ── 8. Convert back to BGR (PaddleOCR expects BGR or path) ────────────────

    result = cv2.cvtColor(cleaned, cv2.COLOR_GRAY2BGR)

    log.info("  Preprocessing complete")

    return result





def _deskew(gray: np.ndarray) -> np.ndarray:

    """Detect and correct rotation of a skewed receipt."""

    try:

        edges = cv2.Canny(gray, 50, 150, apertureSize=3)

        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100,

                                 minLineLength=100, maxLineGap=10)

        if lines is None:

            return gray



        angles = []

        for line in lines:

            x1, y1, x2, y2 = line[0]

            if x2 != x1:

                angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))

                if -45 < angle < 45:          # ignore near-vertical lines

                    angles.append(angle)



        if not angles:

            return gray



        median_angle = float(np.median(angles))

        if abs(median_angle) < 0.5:           # no correction needed

            return gray



        log.info(f"  Deskewing by {median_angle:.1f}°")

        h, w   = gray.shape

        center = (w // 2, h // 2)

        M      = cv2.getRotationMatrix2D(center, median_angle, 1.0)

        return cv2.warpAffine(gray, M, (w, h),

                               flags=cv2.INTER_CUBIC,

                               borderMode=cv2.BORDER_REPLICATE)

    except Exception as e:

        log.warning(f"  Deskew failed (non-critical): {e}")

        return gray





def save_preprocessed(img_array: np.ndarray, original_path: str) -> str:

    """Save the preprocessed image to disk and return its path."""

    p       = Path(original_path)

    out     = p.parent / f"_pre_{p.name}"

    cv2.imwrite(str(out), img_array)

    return str(out)





# ═══════════════════════════════════════════════════════════════════════════════

# STEP 2 — RAW OCR (PaddleOCR → EasyOCR fallback)

# ═══════════════════════════════════════════════════════════════════════════════



_paddle_reader = None   # lazy-loaded singleton



def _get_paddle():

    global _paddle_reader

    if _paddle_reader is None:

        log.info("Loading PaddleOCR (first call — may take 30s)…")

        from paddleocr import PaddleOCR

        # PaddleOCR v3+: use_angle_cls and show_log removed
        # Note: PaddleOCR does NOT support Tamil natively
        # Tamil bills will be extracted via Gemini Vision API instead

        _paddle_reader = PaddleOCR(lang="en")

        log.info("PaddleOCR loaded ✓ (English only — Tamil via Gemini Vision API)")

    return _paddle_reader





def run_paddle_ocr(image_path: str) -> str:

    """Run PaddleOCR v3 and return extracted text."""

    ocr = _get_paddle()

    lines_out = []

    log.info(f"  Running PaddleOCR on: {image_path}")

    try:

        results = list(ocr.predict(image_path))

        log.info(f"  PaddleOCR predict() returned {len(results)} result(s)")

        for res in results:

            rec_texts  = res["rec_texts"]

            rec_scores = res["rec_scores"]

            log.info(f"  rec_texts count: {len(rec_texts)}")

            for text, score in zip(rec_texts, rec_scores):

                if float(score) > 0.4 and str(text).strip():

                    lines_out.append(str(text).strip())



        if lines_out:

            joined = "\n".join(lines_out)

            log.info(f"  PaddleOCR extracted {len(lines_out)} lines ({len(joined)} chars)")

            return joined



        log.warning("  PaddleOCR returned 0 usable text lines")

    except Exception as e:

        import traceback

        log.warning(f"  PaddleOCR failed: {e}")

        log.warning(traceback.format_exc())



    return ""



def run_easyocr_fallback(image_path: str) -> str:
    """EasyOCR disabled — NumPy 2.x incompatibility. Gemini Vision handles Tamil."""
    log.warning("EasyOCR skipped. Gemini Vision will handle Tamil extraction.")
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# LANGUAGE / SCRIPT DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def _tesseract_available() -> bool:
    """Return True if the Tesseract binary is reachable."""
    import shutil as _sh
    # First check the configured path
    if _TESS_CMD and os.path.isfile(str(_TESS_CMD)):
        return True
    # Also check PATH
    if _sh.which("tesseract"):
        return True
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _detect_script(image_path: str) -> str:
    """
    Detect whether a bill is English-only, Tamil-only, or mixed.

    If Tesseract is not installed → returns "english" so PaddleOCR handles it
    and Gemini Vision does the structured extraction (works for both scripts).

    Returns: "english" | "tamil" | "mixed"
    """
    if not _tesseract_available():
        log.warning(
            "  Tesseract not installed — defaulting to english "
            "(PaddleOCR + Gemini Vision will handle all scripts)"
        )
        return "english"
    try:
        img    = Image.open(image_path).convert("RGB")
        sample = pytesseract.image_to_string(
            img, lang="tam+eng", config="--oem 1 --psm 6"
        )
        alpha  = [c for c in sample if c.isalpha()]
        tamil  = [c for c in alpha if "\u0b80" <= c <= "\u0bff"]
        if not alpha:
            return "english"
        ratio  = len(tamil) / len(alpha)
        script = "tamil" if ratio >= 0.50 else ("mixed" if ratio >= 0.15 else "english")
        log.info(
            "  Script detect: %s  (Tamil %.0f%% of %d alpha chars)",
            script, ratio * 100, len(alpha),
        )
        return script
    except Exception as exc:
        log.warning("  Script detection error (%s) — defaulting to english", exc)
        return "english"


def run_tesseract_ocr(image_path: str, lang: str = "tam+eng") -> str:
    """
    Run Tesseract OCR for Tamil or mixed bills.

    lang: "eng" | "tam" | "tam+eng"
    Returns extracted text or "" on failure/not-installed.
    """
    if not _tesseract_available():
        log.warning("  Tesseract not found — skipping (Gemini Vision will extract fields)")
        return ""
    try:
        img  = Image.open(image_path).convert("RGB")
        text = pytesseract.image_to_string(
            img, lang=lang, config="--oem 1 --psm 6"
        ).strip()
        log.info("  Tesseract (%s) extracted %d chars", lang, len(text))
        return text
    except Exception as exc:
        log.warning("  Tesseract OCR failed: %s", exc)
        return ""


def extract_raw_text(image_path: str) -> str:
    """
    Route to the correct local OCR engine based on detected script.

    Decision table
    ──────────────────────────────────────────────────────────────
    Script   │ Primary engine        │ Fallback
    ─────────┼───────────────────────┼────────────────────────────
    english  │ PaddleOCR             │ Tesseract eng (if installed)
    tamil    │ Tesseract tam+eng     │ PaddleOCR (partial digits)
    mixed    │ Tesseract tam+eng     │ + PaddleOCR  (concatenated)
    ──────────────────────────────────────────────────────────────
    NOTE: If Tesseract is not installed, ALL routes fall back to
    PaddleOCR for raw text.  Gemini Vision API always runs after
    this step and handles Tamil fields directly from the image.
    """
    script = _detect_script(image_path)

    if script == "english":
        log.info("  → English bill: PaddleOCR")
        text = run_paddle_ocr(image_path)
        if not text.strip():
            log.info("  PaddleOCR empty — trying Tesseract eng fallback")
            text = run_tesseract_ocr(image_path, lang="eng")
        return text

    elif script == "tamil":
        log.info("  → Tamil bill: Tesseract tam+eng")
        text = run_tesseract_ocr(image_path, lang="tam+eng")
        if not text.strip():
            log.info("  Tesseract empty — Gemini Vision will extract Tamil fields")
        return text

    else:  # mixed
        log.info("  → Mixed Tamil+English bill: Tesseract tam+eng + PaddleOCR")
        tess   = run_tesseract_ocr(image_path, lang="tam+eng")
        paddle = run_paddle_ocr(image_path)
        parts  = [p for p in [tess, paddle] if p.strip()]
        combined = "\n".join(parts)
        log.info(
            "  Combined OCR: Tesseract=%d  PaddleOCR=%d  total=%d chars",
            len(tess), len(paddle), len(combined),
        )
        return combined





# ═══════════════════════════════════════════════════════════════════════════════

# STEP 3 — STRUCTURED EXTRACTION via Google Gemini Vision API (free)

# ═══════════════════════════════════════════════════════════════════════════════



GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")  # Load from api.env, fallback to empty
GEMINI_URL     = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


def _get_api_key() -> str:
    """Get Gemini API key from environment or global variable."""
    # Check environment first (most current)
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        return env_key
    return GEMINI_API_KEY


def _resolve_gemini_url() -> str:
    """Get Gemini API URL from environment or global variable."""
    return os.getenv("GEMINI_URL", GEMINI_URL)


def _gemini_http():
    """Return a requests session that ignores broken system proxy env vars."""
    import requests

    session = requests.Session()
    session.trust_env = False
    return session


# Check API key availability on startup
_api_status = "✅ Gemini Vision API key loaded" if _get_api_key() else "⚠️ No Gemini API key — using OCR + regex fallback"
log.info(f"{_api_status}")





def _clean_gemini_json(raw: str) -> dict:
    """
    Robustly parse Gemini's JSON response which may contain:
      - Markdown fences (```json ... ```)
      - Trailing commas before } or ]
      - // line comments
      - Python None / True / False literals
      - Single-quoted strings

    Tries standard json.loads first; falls back to regex cleaning; finally
    tries the json5 library if installed.
    """
    # 1. Strip markdown fences and whitespace
    raw = re.sub(r"```json\s*|```", "", raw).strip()

    # Quick attempt with standard json
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 2. Apply cleaning passes
    cleaned = raw
    # Remove // line comments (not inside strings — good enough for Gemini output)
    cleaned = re.sub(r"(?m)//[^\n]*$", "", cleaned)
    # Remove trailing commas before } or ]
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    # Replace Python None/True/False with JSON null/true/false
    cleaned = re.sub(r"\bNone\b",  "null",  cleaned)
    cleaned = re.sub(r"\bTrue\b",  "true",  cleaned)
    cleaned = re.sub(r"\bFalse\b", "false", cleaned)
    # Replace single-quoted strings with double-quoted (simple cases)
    cleaned = re.sub(r"'([^']*)'", r'"\1"', cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. Try json5 if available (handles all the above natively)
    try:
        json5 = importlib.import_module("json5")
        return json5.loads(raw)
    except (ImportError, Exception):
        pass

    # 4. Give up — re-raise with the cleaned text for easier debugging
    raise json.JSONDecodeError(
        "Could not parse Gemini JSON after cleaning", cleaned, 0
    )


def _normalize_gemini_vision_output(data: dict) -> dict:
    """Convert Gemini Vision invoice-style output into the app's expected schema."""
    if not isinstance(data, dict):
        return data

    if "invoice_header" not in data and "seller_information" not in data:
        return data

    normalized = {}
    header = data.get("invoice_header", {}) or {}
    seller = data.get("seller_information", {}) or {}
    customer = data.get("customer_information", {}) or {}
    delivery = data.get("delivery_payment_details", {}) or {}

    normalized["vendor_name"] = seller.get("name") or data.get("vendor_name")
    normalized["vendor_phone"] = seller.get("phone") or data.get("vendor_phone")
    normalized["vendor_gstin"] = seller.get("gstin") or data.get("vendor_gstin")
    normalized["invoice_no"] = header.get("bill_no") or data.get("invoice_no")
    normalized["date"] = header.get("date") or data.get("date")
    normalized["bill_type"] = (data.get("bill_type") or header.get("invoice_type") or "tax_invoice").lower()
    normalized["payment_by"] = delivery.get("payment_by") or data.get("payment_by")

    items = []
    for item in data.get("line_items", []) or []:
        if not isinstance(item, dict):
            continue
        items.append({
            "name": item.get("product_name") or item.get("name"),
            "qty": item.get("qty"),
            "unit": item.get("unit") or item.get("uom") or None,
            "rate": item.get("rate"),
            "amount": item.get("amount") or item.get("value"),
        })

    if items:
        normalized["items"] = items

    for numeric_key in ("subtotal", "discount", "cgst", "sgst", "igst", "total_tax", "total_amount"):
        if numeric_key in data:
            normalized[numeric_key] = data[numeric_key]

    if "currency" in data:
        normalized["currency"] = data["currency"]

    return normalized


def _extract_structured_data_via_text_gemini(ocr_text: str) -> dict:

    """Legacy helper: send OCR text to Gemini for structured extraction."""

    api_key = _get_api_key()
    url = _resolve_gemini_url()

    if not api_key or not url:

        return {"raw_text": ocr_text, "error": "No Gemini API key configured"}



    import requests

    # Use rate limiting from queue

    queue = get_queue()

    queue.wait_if_needed()

    

    prompt = VISION_PROMPT + f"\n\nOCR TEXT TO PARSE:\n{ocr_text}"

    

    retry_config = get_retry_config()

    quality_tracker = get_quality_tracker()

    

    for attempt in range(retry_config.max_attempts):

        try:

            resp = _gemini_http().post(

                f"{url}?key={api_key}",

                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"temperature": 0, "maxOutputTokens": 4096,
                                           "response_mime_type": "application/json"}},

                timeout=60,

            )

            resp.raise_for_status()

            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]

            raw = re.sub(r"```json|```", "", raw).strip()

            data = _clean_gemini_json(raw)

            quality_tracker.record_success("vision")

            log.info(f"  Gemini text extraction OK — {len(data.get('items', []))} items")

            return data

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:

                quality_tracker.record_rate_limit()

                if attempt < retry_config.max_attempts - 1:

                    wait_time = retry_config.get_wait_time(attempt)

                    log.warning(f"  Rate limited (429). Retrying in {wait_time:.1f}s (attempt {attempt + 1}/{retry_config.max_attempts})…")

                    time.sleep(wait_time)

                    continue

                else:

                    log.error(f"  Gemini text API: Max retries exceeded (429)")

                    return {"raw_text": ocr_text, "error": "Rate limited (429) — API quota exhausted"}

            safe_msg = str(e).split("?key=")[0]

            log.error(f"  Gemini text API error: {safe_msg}")

            return {"raw_text": ocr_text, "error": safe_msg}

        except Exception as e:

            safe_msg = str(e).split("?key=")[0]

            log.error(f"  Gemini text API error: {safe_msg}")

            return {"raw_text": ocr_text, "error": safe_msg}

    

    return {"raw_text": ocr_text, "error": "Max retries exceeded (429 rate limit)"}





# ═══════════════════════════════════════════════════════════════════════════════

# STEP 3-B — GEMINI VISION (direct image → structured data, best for Tamil)

# ═══════════════════════════════════════════════════════════════════════════════



VISION_PROMPT = """You are reading an Indian shop bill or GST tax invoice photo.

The paper may be wrinkled or crumpled. Text may be in Tamil, English, or both.



Extract all information and return ONLY one valid flat JSON object with the exact keys shown below (no markdown, no explanation, no nested objects):



{

  "vendor_name":   "shop/company name",

  "vendor_phone":  "phone number or null",

  "vendor_gstin":  "GSTIN or null",

  "invoice_no":    "invoice/bill/Q number or null",

  "date":          "YYYY-MM-DD or null",

  "bill_type":     "estimate | tax_invoice | receipt",

  "items": [

    {

      "name":   "item name in English (translate Tamil to English)",

      "qty":    number_or_null,

      "unit":   "string or null",

      "rate":   number_or_null,

      "amount": number

    }

  ],

  "subtotal":     number_or_null,

  "discount":     number_or_null,

  "cgst":         number_or_null,

  "sgst":         number_or_null,

  "igst":         number_or_null,

  "total_tax":    number_or_null,

  "total_amount": number,

  "currency":     "INR"

}



Rules:

- All amounts must be plain numbers (no Rs, no commas)

- Translate Tamil item names to English

- total_amount = final payable (look for Total / Net Payable / Bill Amount)

- Missing fields = null, not 0



Tamil hints: பொருள்=Product, விலை=Price, தொகை=Total, தேதி=Date,

துவரம்பருப்பு=Toor Dal, கோல்டுகிங்=Goldking, சிறுதானிய=Millet"""





def extract_via_vision_api(image_path: str) -> dict:

    """

    Send image directly to Gemini Vision for structured Tamil+English extraction.

    Features:

    - Request caching (avoid duplicate API calls for same bill)

    - Rate limiting (max 10 req/min, prevents queue overflow)

    - Smart retry with exponential backoff + jitter

    - Quality tracking (monitor degradation)

    """

    api_key = _get_api_key()
    url = _resolve_gemini_url()

    if not api_key:

        return {"error": "No Gemini API key — set GEMINI_API_KEY env variable"}

    if not url:

        return {"error": "Gemini API URL is not configured"}



    import requests

    # ── STEP 1: Check cache ─────────────────────────────────────────────────

    cache = get_cache()

    cached = cache.get(image_path)

    if cached:

        get_quality_tracker().record_success("cache")

        return cached



    # ── STEP 2: Wait for rate limit slot ────────────────────────────────────

    queue = get_queue()

    queue.wait_if_needed()



    # ── STEP 3: Prepare request ─────────────────────────────────────────────

    with open(image_path, "rb") as f:

        image_data = base64.b64encode(f.read()).decode("utf-8")



    suffix     = Path(image_path).suffix.lower()

    media_map  = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",

                  ".png": "image/png",  ".webp": "image/webp"}

    media_type = media_map.get(suffix, "image/jpeg")



    # ── STEP 4: Retry with exponential backoff + jitter ────────────────────

    retry_config = get_retry_config()

    quality_tracker = get_quality_tracker()



    for attempt in range(retry_config.max_attempts):

        try:

            resp = _gemini_http().post(

                f"{url}?key={api_key}",

                json={

                    "contents": [{

                        "parts": [

                            {"inline_data": {"mime_type": media_type, "data": image_data}},

                            {"text": VISION_PROMPT},

                        ]

                    }],

                    "generationConfig": {
                        "temperature": 0,
                        "maxOutputTokens": 4096,
                        "response_mime_type": "application/json",
                    },

                },

                timeout=90,

            )

            resp.raise_for_status()

            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]

            raw = re.sub(r"```json|```", "", raw).strip()

            data = _clean_gemini_json(raw)
            data = _normalize_gemini_vision_output(data)

            

            # ✓ Success — cache it

            cache.set(image_path, data)

            quality_tracker.record_success("vision")

            log.info(f"  Gemini Vision OK — vendor={data.get('vendor_name')}, total={data.get('total_amount')}")

            return data



        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:

                quality_tracker.record_rate_limit()

                if attempt < retry_config.max_attempts - 1:

                    wait_time = retry_config.get_wait_time(attempt)

                    log.warning(f"  Rate limited (429). Retrying in {wait_time:.1f}s (attempt {attempt + 1}/{retry_config.max_attempts})…")

                    time.sleep(wait_time)

                    continue

                else:

                    # All retries exhausted

                    log.error(f"  Gemini Vision: Max retries exceeded (429 rate limit). Quota may be exhausted.")

                    response = {"error": "Rate limited (429) — API quota exhausted"}

                    return response

            safe_msg = str(e).split("?key=")[0]

            log.error(f"  Gemini Vision error: {safe_msg}")

            return {"error": safe_msg}

        except json.JSONDecodeError as e:

            log.error(f"  Gemini Vision JSON error: {e}\n  Raw output snippet: {raw[:1000]}")

            return {"error": f"JSON parse failed: {e}"}

        

        except Exception as e:

            safe_msg = str(e).split("?key=")[0]

            log.error(f"  Gemini Vision error: {safe_msg}")

            return {"error": safe_msg}

    

    return {"error": "Max retries exceeded (429 rate limit)"}





# ═══════════════════════════════════════════════════════════════════════════════

# API QUALITY & CACHE STATS (exposed for monitoring dashboard)

# ═══════════════════════════════════════════════════════════════════════════════



def get_api_quality_stats() -> dict:

    """

    Get current API quality metrics.

    Useful for monitoring dashboard to detect when quota is exhausted.

    Returns:

      {

        "total_requests": N,

        "success_rate_pct": "X%",

        "vision_api_failures": N,

        "rate_limit_errors": N,

        "regex_fallbacks": N,

        "cache_hits": N (estimated)

      }

    """

    tracker = get_quality_tracker()

    return tracker.get_summary()





def clear_api_cache() -> dict:

    """Clear all cached bill responses. Useful for testing or quota reset."""

    cache = get_cache()

    cache.clear()

    log.info("✓ API cache cleared")

    return {"status": "cache_cleared"}





# ═══════════════════════════════════════════════════════════════════════════════

# STEP 4 — POST-PROCESSING & VALIDATION

# ═══════════════════════════════════════════════════════════════════════════════



def _clean_amount(val) -> Optional[float]:

    """Parse messy amount strings like '1,951.00' or '₹1951' → 1951.0. Validates amount is reasonable."""

    if val is None:

        return None

    s = str(val).replace("₹", "").replace(",", "").strip()

    try:

        amount = float(s)

        # Reject obviously wrong values (negative, zero, or absurdly large)

        # Reasonable bill amounts: ₹10 to ₹9,999,999 (about $120k USD)

        if amount <= 0 or amount > 10_000_000:

            log.warning(f"  Amount rejected (out of range): {amount}")

            return None

        return amount

    except ValueError:

        return None





def validate_and_clean(data: dict) -> dict:

    """Validate extracted data and fix obvious issues."""

    if not isinstance(data, dict):

        return {"error": "Structured OCR data must be a dictionary", "success": False}

    if not isinstance(data.get("items"), list):

        data["items"] = []

    # Clean numeric fields

    for field in ["subtotal", "discount", "cgst", "sgst", "igst",

                  "total_tax", "total_amount"]:

        if field in data:

            data[field] = _clean_amount(data[field])



    # Sanity check: Indian shop bills rarely exceed ₹1,00,000

    # If total is absurd, it picked up a phone/HSN/address number — discard it

    total = data.get("total_amount")

    if total and total > 100000:

        log.warning(f"  Sanity check: total {total} > 1,00,000 — discarding as likely OCR error")

        data["total_amount"] = None

        data["success"] = False



    # Clean items

    for item in data.get("items", []):

        if item.get("name"):

            item["name"] = _translate_item_name(str(item["name"]).strip())

        item["amount"] = _clean_amount(item.get("amount")) or 0

        item["rate"]   = _clean_amount(item.get("rate"))

        if item.get("qty") is not None:

            try:

                item["qty"] = float(str(item["qty"]).replace(",", ""))

            except:

                item["qty"] = None



    if not data.get("total_amount") and data.get("items"):

        items_sum = round(sum(i.get("amount", 0) for i in data["items"]), 2)

        if items_sum > 0:

            data["total_amount"] = items_sum

    # Validate total vs sum of items

    if data.get("items") and data.get("total_amount"):

        items_sum = sum(i.get("amount", 0) for i in data["items"])

        declared  = data["total_amount"]

        diff      = abs(items_sum - declared)

        if diff > 5:   # allow ₹5 rounding

            log.warning(f"  Total mismatch: items_sum={items_sum:.2f} declared={declared:.2f} diff={diff:.2f}")

            data["_validation_warning"] = f"Items sum ₹{items_sum:.2f} ≠ declared total ₹{declared:.2f}"

        else:

            data["_validation_ok"] = True



    # Date cleanup — ensure YYYY-MM-DD

    raw_date = data.get("date")

    if raw_date:

        data["date"] = _normalize_date(raw_date)



    return data





def _normalize_date(raw: str) -> Optional[str]:

    """Try to parse various date formats and return YYYY-MM-DD. Returns None if unparseable."""

    if not raw or not isinstance(raw, str):

        return None

    

    formats = [

        "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d",

        "%d/%m/%y", "%d-%b-%y", "%d-%b-%Y",

        "%d.%m.%Y",

    ]

    from datetime import datetime

    for fmt in formats:

        try:

            parsed = datetime.strptime(raw.strip(), fmt)

            # Validate year is reasonable (1900-2100)

            if 1900 <= parsed.year <= 2100:

                return parsed.strftime("%Y-%m-%d")

        except:

            pass

    return None   # return None if unparseable (instead of returning raw garbage)





# ═══════════════════════════════════════════════════════════════════════════════

# MAIN PUBLIC API

# ═══════════════════════════════════════════════════════════════════════════════



def is_supported_image(content_type: str) -> bool:

    """Check if a MIME type is an accepted image format."""

    ct = (content_type or "").lower().split(";")[0].strip()

    return ct in {

        "image/jpeg", "image/jpg", "image/png", "image/webp",

        "image/bmp", "image/tiff", "image/gif",

        "application/octet-stream",   # canvas blob fallback

    }






def _gemini_enhance(ocr_text, api_key):
    import json as js
    url = _resolve_gemini_url()
    if not url: return {}
    p = "From this Indian bill OCR text, return ONLY this JSON (no markdown):\n"
    p += "{\"vendor_name\": \"shop name in English\", \"total_amount\": 0, \"date\": \"YYYY-MM-DD\"}\n"
    p += "Translate Tamil shop names to English.\n\nOCR TEXT:\n" + ocr_text[:1500]
    try:
        r = _gemini_http().post(f"{url}?key={api_key}",
            json={"contents":[{"parts":[{"text":p}]}],
                  "generationConfig":{"temperature":0,"maxOutputTokens":200,
                                      "response_mime_type":"application/json"}},
            timeout=15)
        if r.status_code == 429: return {}
        r.raise_for_status()
        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        raw = raw.strip().replace("`json","").replace("`","").strip()
        return js.loads(raw)
    except Exception:
        return {}


def _merge_missing_fields(target: dict, source: dict, fields: tuple[str, ...]) -> dict:
    """Fill missing keys in target using values from source."""
    if not source:
        return target

    for field in fields:
        if not target.get(field) and source.get(field):
            target[field] = source[field]

    return target

def process_bill(

    image_path : str,

    use_vision : bool = True,    # True = send image to Gemini Vision (most accurate)

    use_ocr    : bool = True,    # True = run PaddleOCR first

    save_debug : bool = False,   # True = save preprocessed image to disk

) -> dict:

    """

    Full pipeline: image → preprocessed → OCR → structured JSON



    Args:

        image_path : path to bill image (JPG/PNG)

        use_vision : use Gemini Vision API directly on the image (best for Tamil)

        use_ocr    : run PaddleOCR text extraction

        save_debug : save the preprocessed image (for debugging)



    Returns:

        dict with all extracted fields

    """

    log.info(f"{'─'*60}")

    log.info(f"Processing: {image_path}")



    result = {

        "source_file": image_path,

        "ocr_text":    "",

        "error":       None,

    }

    temp_proc_path = None



    try:

        # Step 1: Preprocess

        preprocessed = preprocess_image(image_path)

        if save_debug:

            debug_path = save_preprocessed(preprocessed, image_path)

            log.info(f"  Debug image: {debug_path}")

            proc_path = debug_path

        else:

            # Write to temp file for OCR libraries

            import tempfile

            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)

            cv2.imwrite(tmp.name, preprocessed)
            tmp.close()

            proc_path = tmp.name
            temp_proc_path = tmp.name



        # Step 2: Raw OCR text

        if use_ocr:

            raw_text = extract_raw_text(proc_path)

            result["ocr_text"] = raw_text

            log.info(f"  Raw OCR lines: {len(raw_text.splitlines())}")



        # Step 3: Gemini Vision (direct image → JSON; best for Tamil AND English)
        api_key    = _get_api_key()
        structured = {}
        _src_tag   = "ocr_regex"   # will be updated below

        if use_vision and api_key:
            log.info("  Attempting Gemini Vision API…")
            try:
                vision_result = extract_via_vision_api(image_path)
                if vision_result and not vision_result.get("error"):
                    structured = vision_result
                    _src_tag   = "gemini_vision"
                    log.info(
                        "  ✓ Gemini Vision: vendor=%s  total=%s  date=%s",
                        structured.get("vendor_name"),
                        structured.get("total_amount"),
                        structured.get("date"),
                    )
                else:
                    err = (vision_result.get("error", "Unknown") if vision_result
                           else "No response")
                    log.warning("  Gemini Vision returned error: %s", err)
                    # Propagate 429 so main.py can return HTTP 429
                    if "429" in str(err):
                        result["error"] = err
            except Exception as exc:
                log.warning("  Gemini Vision failed: %s — falling back to OCR+regex", exc)
        elif not api_key:
            log.warning("  No Gemini API key — skipping Vision API")
        
        # Step 3b: If Gemini Vision missed fields, refine via Gemini text API
        if use_vision and api_key and result["ocr_text"].strip():
            needs_refinement = (
                not structured
                or not structured.get("vendor_name")
                or not structured.get("total_amount")
                or not structured.get("date")
            )
            if needs_refinement:
                log.info("  Gemini text-refinement pass…")
                gemini_text_func = globals().get("_gemini_enhance")
                if gemini_text_func:
                    enhanced = gemini_text_func(result["ocr_text"], api_key)
                    structured = _merge_missing_fields(
                        structured or {},
                        enhanced,
                        ("vendor_name", "total_amount", "date"),
                    )
                    if enhanced and _src_tag == "ocr_regex":
                        _src_tag = "gemini_text"
                else:
                    log.warning("  Gemini text-refinement skipped because _gemini_enhance is unavailable")

        # Step 3c: Smart regex fallback — fills any remaining gaps from local OCR text
        #   English bill  → fed from PaddleOCR text
        #   Tamil bill    → fed from Tesseract tam+eng text
        #   Mixed bill    → fed from Tesseract+PaddleOCR combined text
        if not structured or not structured.get("vendor_name"):
            log.info("  Smart regex fallback…")
            regex_result = _smart_extract(result["ocr_text"])
            if not structured:
                structured = regex_result
                _src_tag   = "ocr_regex"
            else:
                structured = _merge_missing_fields(
                    structured,
                    regex_result,
                    ("vendor_name", "total_amount", "date",
                     "vendor_phone", "vendor_gstin", "items"),
                )

        # Stamp which engine produced the final structured data
        structured["_source"] = _src_tag


        # Step 4: Validate

        structured = validate_and_clean(structured)

        result.update(structured)

        result["success"] = bool(
            not structured.get("error")
            and (
                result.get("total_amount")
                or (
                    result.get("vendor_name")
                    and result.get("vendor_name") != "Unknown Vendor"
                )
                or result.get("items")
                or result.get("date")
            )
        )



    except Exception as e:

        log.error(f"  Pipeline error: {e}\n{traceback.format_exc()}")

        result["error"]   = str(e)

        result["success"] = False


    finally:

        if temp_proc_path:

            try:

                Path(temp_proc_path).unlink(missing_ok=True)

            except Exception as cleanup_err:

                log.warning(f"  Temp cleanup failed for {temp_proc_path}: {cleanup_err}")

    return result





# ── Regex-based fallback (no API key) ─────────────────────────────────────────


# Tamil-English common vendors and items mapping
TAMIL_VENDOR_MAP = {
    "Bharathi Agencies": ["bharathi", "bharath"],
    "Mythili Sales": ["mythili"],
    "Joseph Store": ["joseph", "store"],
    "Gem Provision Stores": ["gem", "provision"],
    "Lakshmi Store": ["lakshmi"],
    "Sri Vella Wholesale": ["vella", "wholesale"],
    "Abhinaya Provisions": ["abhinaya", "abhinayaa", "அபிநயா", "புரவிசன்ஸ்", "provisions"],
}

TAMIL_ITEM_MAP = {
    "Rice": ["rice", "arisi", "அரிசி"],
    "Oil": ["oil", "oil", "ennai", "எண்ணை"],
    "Dhal": ["dhal", "dal", "paruppu", "பருப்பு", "toor", "tuvar"],
    "Spices": ["spice", "masala", "மசாலா"],
    "Milk": ["milk", "paal", "பால்"],
    "Sugar": ["sugar", "sakarai", "சக்கரை"],
    "Salt": ["salt", "uppu", "உப்பு"],
    "Vegetables": ["vegetable", "kari", "காய்"],
    "Provisions": ["provision", "grocery", "general"],
    "Pongal": ["pongal", "பொங்கல்", "பொங்கல"],
    "Kashmir": ["kashmir", "கஸ்மீர்"],
    "Pandan": ["pandan", "பண்டல்", "பண்டல்"],
    "Mint": ["mint", "மென்ட்", "மென்ட"],
    "Soap": ["soap", "சோப்"],
    "Toothpaste": ["toothpaste", "தூத்", "பேஸ்ட்"],
    "Milk Powder": ["milk powder", "மில்க் பவுடர்"],
}


def _transliterate_tamil_text(text: str) -> str:
    """
    Clean up garbled OCR Tamil text by identifying common patterns.
    Returns Romanized/English approximation of Tamil words.
    """
    # This is a simple approach - for production, use a proper transliteration library
    # like 'Indic' library for better accuracy
    
    if not text or len(text) < 3:
        return text
    
    text_lower = text.lower()
    
    # Try to identify if this looks like garbled Tamil
    # Garbled text often has: non-standard patterns, multiple consonants, etc.
    # For now, we'll return the text as-is if it seems like vendor names
    
    # Check if text contains common vendor patterns
    for proper_name, variants in TAMIL_VENDOR_MAP.items():
        for variant in variants:
            if variant in text_lower:
                return proper_name
    
    # Try to map known Tamil item fragments too
    for item_name, variants in TAMIL_ITEM_MAP.items():
        for variant in variants:
            if variant in text_lower:
                return item_name

    return text


def _translate_item_name(name: str) -> str:
    """Translate a Tamil/garbled item description into an English label."""
    if not name or len(name) < 3:
        return name
    normalized = name.lower()
    for item_name, variants in TAMIL_ITEM_MAP.items():
        for variant in variants:
            if variant in normalized:
                return item_name
    # If the name contains Tamil script, preserve it but normalize spacing
    if re.search(r"[\u0b80-\u0bff]", name):
        cleaned = re.sub(r"[^\w\s\-\[\]\(\)/]", "", name)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned
    return name


def _clean_vendor_name(name: str) -> str:
    """Clean vendor name from garbled OCR text."""
    if not name or len(name) < 3:
        return "Unknown Vendor"

    normalized = name.lower()
    for proper_name, variants in TAMIL_VENDOR_MAP.items():
        if any(variant.lower() in normalized for variant in variants):
            return proper_name

    name = _transliterate_tamil_text(name)

    # Remove common OCR garbage patterns
    name = re.sub(r"[^\w\s\-&.]", "", name)  # Remove special chars except common ones
    name = re.sub(r"\s+", " ", name).strip()  # Normalize spaces

    if any(token in name.lower() for token in [
        "mobile", "phone", "time", "date", "qty", "amount", "total", "estimate"
    ]):
        return "Unknown Vendor"

    # If it looks like garbage (many repeated chars or very short after cleanup)
    if len(name) < 3 or re.search(r"(.)\1{3,}", name):
        return "Unknown Vendor"

    if name.isupper() and len(name.split()) <= 4:
        return name.title()

    return name


def _smart_extract(text: str) -> dict:

    """

    Smart regex extraction for all Tamil Nadu bill types.

    Handles:

      - Tamil estimate bills  (Total : 1951.00)

      - Distributor invoices  (Net Payable : 747.00)

      - Sales invoices        (Bill Amount : 1,261.00)

      - Tax invoices          (Total  ₹ 839.00)

    """

    lines = text.splitlines()



    # ── TOTAL AMOUNT (most important) ──────────────────────────────────────────

    total = _smart_extract_total(lines, text)



    # ── VENDOR NAME ────────────────────────────────────────────────────────────

    vendor_name = "Unknown Vendor"

    skip = ["estimate","invoice","tax invoice","mobile","phone","gstin",

            "fssai","time","date","serial","bill to","from","shipping",

            "state","pan","iec","items","qty","total","amount",

            "original","duplicate","subject","jurisdiction","computer",

            "daled","dated","invoice no","buyer","contact","e-mail","email"]

    # Collect vendor candidates from header lines only.

    candidates = []

    for idx, line in enumerate(lines[:20]):

        s = line.strip()
        lower_s = s.lower()

        if re.search(r"\bqty\b|\brate\b|\bamount\b", lower_s):
            break

        if not s or len(s) < 4 or len(s) > 70: continue

        if any(k in lower_s for k in skip): continue

        if re.match(r"^[\d\s\W]+$", s): continue

        alpha = sum(c.isalpha() for c in s) / max(len(s), 1)

        if alpha >= 0.35:  # Lowered threshold to catch more names

            # Clean up OCR garbage before adding as candidate
            cleaned = _clean_vendor_name(s)
            if len(cleaned) > 3:
                candidates.append((cleaned, idx))

    # Prefer lines with business keywords (stronger priority)

    biz_words = ["agenc","store","shop","trade","mart","provision","medic",

                 "pharma","hotel","restaur","general","super","whole","retail",

                 "distribut","enterprise","industri","sales","corp","co.","ltd","pvt"]

    best_match = None

    best_score = -1

    
    for c, idx in candidates:

        c_lower = c.lower()

        score = 0

        

        # Check for business keywords

        for w in biz_words:

            if w in c_lower:

                score += 10

        

        # Penalize lines with too many digits (likely addresses or amounts)

        digit_ratio = sum(ch.isdigit() for ch in c) / max(len(c), 1)

        if digit_ratio > 0.3:

            score -= 5

        

        # Prefer longer names (more likely to be shop name)

        score += len(c) * 0.1

        # Prefer earlier header lines over text closer to the item table.
        score += max(0, 10 - idx) * 0.4

        

        # Penalize lines that look like item names

        if any(x in c_lower for x in ["piece", "kg", "liter", "pack", "box"]):

            score -= 10

        if idx >= 8 and not any(w in c_lower for w in biz_words):

            score -= 4

        

        if score > best_score:

            best_score = score

            best_match = c

    if best_match and best_score >= 4:

        vendor_name = best_match

    elif candidates:

        # Fallback: longest candidate that is not digit-heavy

        clean_candidates = [c for c, idx in candidates

                           if idx < 8 and sum(ch.isdigit() for ch in c) / max(len(c),1) < 0.3]

        if clean_candidates:

            vendor_name = max(clean_candidates, key=len)

        elif any(any(w in c.lower() for w in biz_words) for c, _ in candidates):

            vendor_name = max((c for c, _ in candidates), key=len)



    # ── DATE ───────────────────────────────────────────────────────────────────

    date = None

    # Fix OCR month typos: Fcb->Feb, Jan->Jan, Mar->Mar etc.

    text_d = (text

        .replace("Fcb","Feb").replace("FCB","Feb")

        .replace("Jar","Jan").replace("JAR","Jan")

        .replace("Jari","Jan").replace("Jull","Jul")

        .replace("Aur","Apr").replace("Apl","Apr")

        .replace("Ocl","Oct").replace("Noy","Nov")

        .replace("Dcc","Dec").replace("Mer","Mar"))

    # Try DD-Mon-YY format first (e.g. 21-Feb-26)

    dm = re.search(

        r"(\d{1,2})[\-\/\. ](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"

        r"[\-\/\. ](\d{2,4})", text_d, re.IGNORECASE)

    if dm:

        month_map = {"jan":"01","feb":"02","mar":"03","apr":"04","may":"05",

                     "jun":"06","jul":"07","aug":"08","sep":"09","oct":"10",

                     "nov":"11","dec":"12"}

        d, m_str, y = dm.group(1), dm.group(2).lower()[:3], dm.group(3)

        y = "20"+y if len(y)==2 else y

        date = f"{y}-{month_map[m_str]}-{int(d):02d}"

    if not date:

        dm2 = re.search(r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})", text)

        if dm2: date = _normalize_date(dm2.group(1))



    # ── INVOICE NUMBER ─────────────────────────────────────────────────────────

    invoice_no = None

    inv_patterns = [

        r"([A-Z]{2,5}/\d{3,}/[\d\-]+)",          # BAS/3380/25-26

        r"\bQ/(\d+)\b",                             # Q/1234

        r"(?:inv(?:oice)?\s*(?:no|#)|bill\s*no)[:\s]*([A-Z0-9/\-]+)",
        r"\b(A\d{7,})\b",

        r"\b(CXBIL\w+)\b",
    ]

    for pat in inv_patterns:

        m = re.search(pat, text, re.IGNORECASE)

        if m:

            invoice_no = m.group(1) if m.lastindex else m.group(0)

            break



    # ── GSTIN ──────────────────────────────────────────────────────────────────

    gm = re.search(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d])\b", text, re.IGNORECASE)

    gstin = gm.group(1).upper() if gm else None



    # ── PHONE ──────────────────────────────────────────────────────────────────

    pm = re.search(r"(?:mobile|mob|phone|ph|contact)[:\s]*([\d\s\-\+]{10,15})", text, re.IGNORECASE)

    phone = re.sub(r"[^\d]", "", pm.group(1)) if pm else None

    if not phone:

        pm2 = re.search(r"\b([6-9]\d{9})\b", text)

        phone = pm2.group(1) if pm2 else None



    # ── GST ────────────────────────────────────────────────────────────────────

    cgst = _sum_tax_amounts(re.findall(r"CGST[^\d\n]*([\d,]+\.?\d*)", text, re.IGNORECASE))

    sgst = _sum_tax_amounts(re.findall(r"SGST[^\d\n]*([\d,]+\.?\d*)", text, re.IGNORECASE))



    # ── BILL TYPE ──────────────────────────────────────────────────────────────

    bill_type = "tax_invoice" if any(k in text.upper() for k in ["GSTIN","TAX INVOICE","CGST","SGST"]) else "estimate"



    # ── LINE ITEMS ─────────────────────────────────────────────────────────────

    items = []

    for line in lines:

        s = line.strip()

        if not s or len(s) < 8: continue

        if any(k in s.lower() for k in [
            "total", "cgst", "sgst", "discount", "items ", "qty ", "rate ",
            "amount", "mobile", "phone", "invoice", "date", "time"
        ]): continue

        m = re.match(r"^(.+?)\s+(\d+(?:\.\d+)?)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)$", s)

        if m:

            amt = _to_float(m.group(4))

            if amt and 1 <= amt <= 100000:

                items.append({"name": _translate_item_name(m.group(1).strip()), "qty": _to_float(m.group(2)),

                              "rate": _to_float(m.group(3)), "amount": amt})



    return {"vendor_name": vendor_name, "vendor_phone": phone, "vendor_gstin": gstin,

            "invoice_no": invoice_no, "date": date, "bill_type": bill_type,

            "items": items, "cgst": cgst, "sgst": sgst,

            "total_amount": total, "currency": "INR",

            "_source": "paddleocr_regex"}





def _smart_extract_total(lines: list, full_text: str):

    """

    Extract final payable amount — tuned for Tamil Nadu bills.

    Handles OCR typos like Toial, Totai, Tot@l etc.

    """

    # Pre-filter: remove lines that are purely HSN/SAC codes or noise

    clean_lines = []

    for l in lines:

        # Skip lines that are just 6-8 digit codes

        stripped = l.strip()

        if re.match(r"^\d{6,8}$", stripped):

            continue

        # Skip lines with HSN/SAC headers

        if re.search(r"\bHSN\b|\bSAC\b", stripped, re.IGNORECASE) and len(stripped) < 20:

            continue

        clean_lines.append(l)

    lines = clean_lines



    # Normalise OCR typos in a copy of the text

    def _norm(s: str) -> str:

        return (s.lower()

                .replace("toial", "total").replace("totai", "total")

                .replace("tot@l", "total").replace("tota1", "total")

                .replace("lotal", "total").replace("fotal", "total")

                .replace("amound", "amount").replace("chargeab", "chargeable"))

    def _strip_non_amount_patterns(s: str) -> str:

        """Remove date/time substrings so they are not mistaken for totals."""

        month_names = r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"

        s = re.sub(r"\b\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}\b", " ", s)

        s = re.sub(rf"\b\d{{1,2}}[\/\-. ](?:{month_names})[\/\-. ]\d{{2,4}}\b", " ", s, flags=re.I)

        s = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", s)

        return s



    normed_lines = [(_norm(l), l) for l in lines]



    # Priority 1: strong keywords — scan from bottom

    strong_kw = ["net payable", "net amount", "bill amount", "amount payable",

                 "amount chargeable", "amound chargeable", "amound chargeab",

                 "grand total", "total amount", "payable amount",

                 "amount chargeab", "bill amt", "billamt", "netpayable",

                 "round off", "invoice amount", "inv amount"]

    for norm_l, orig_l in reversed(normed_lines):

        if any(kw in norm_l for kw in strong_kw):

            nums = re.findall(r"[\d,]+(?:\.\d{1,2})?", _strip_non_amount_patterns(orig_l))

            valid = [c for c in (_to_float(n) for n in nums) if c and 10 <= c <= 10_000_000]

            if valid:

                amt = max(valid)

                log.info(f"  ✅ Total={amt} from: {orig_l.strip()[:60]}")

                return amt



    # Priority 2: "total" keyword — scan from bottom, skip subtotals/tax lines

    skip_pat = re.compile(

        r"items\s*[:\-]|qty\s*[:\-]|round\s*off|tcs\s|"

        r"scheme.*disc|credit.*note|debit.*note|cess|"

        r"taxable|sub.*total|\d+\.\d+\s*%|cgst\s+\d|sgst\s+\d|"

        r"hsn|sac|\b\d{6,8}\b", re.I)

    for norm_l, orig_l in reversed(normed_lines):

        if skip_pat.search(norm_l):

            continue

        if "total" in norm_l:

            nums = re.findall(r"[\d,]+(?:\.\d{1,2})?", _strip_non_amount_patterns(orig_l))

            valid = [c for c in (_to_float(n) for n in nums) if c and 10 <= c <= 10_000_000]

            if valid:

                amt = max(valid)

                log.info(f"  ✅ Total={amt} from: {orig_l.strip()[:60]}")

                return amt



    # Priority 3: look at next lines after a "total" line (OCR splits label/value)

    for i, (norm_l, orig_l) in enumerate(normed_lines):

        if "total" in norm_l and not skip_pat.search(norm_l):

            for j in range(i, min(i + 5, len(normed_lines))):

                line_text = normed_lines[j][1]

                # Skip lines with HSN codes or purely non-numeric

                if re.search(r"\b\d{6,8}\b", line_text): continue

                nums = re.findall(r"[\d,]+(?:\.\d{1,2})?", _strip_non_amount_patterns(line_text))

                # Filter: must look like a currency amount (has decimal or > 99)

                valid = [c for c in (_to_float(n) for n in nums)

                         if c and 10 <= c <= 100_000

                         and (c != int(c) or c >= 100)]  # prefer decimals or >=100

                if valid:

                    amt = max(valid)

                    log.info(f"  Total={amt} from context near: {orig_l.strip()[:50]}")

                    return amt



    # Priority 4: ₹ symbol — take the largest value

    rupees = re.findall(r"₹\s*([\d,]+(?:\.\d{1,2})?)", full_text)

    valid = [c for c in (_to_float(r) for r in rupees) if c and 50 <= c <= 10_000_000]

    if valid:

        amt = max(valid)

        log.info(f"  ✅ Total={amt} from ₹ symbol")

        return amt



    # Priority 5: largest plausible amount - strip HSN/SAC lines first

    clean_lines = [l for l in full_text.splitlines()

                   if not re.search(r'HSN|SAC', l, re.IGNORECASE)]

    clean_text2 = _strip_non_amount_patterns(' '.join(clean_lines))

    # Remove 6 and 8 digit codes (HSN codes)

    clean_text2 = re.sub(r'\b\d{6}\b', '', clean_text2)

    clean_text2 = re.sub(r'\b\d{8}\b', '', clean_text2)

    all_nums2 = re.findall(r'[\d,]{2,}(?:\.\d{1,2})?', clean_text2)

    valid2 = sorted([c for c in (_to_float(n) for n in all_nums2) if c and 50 <= c <= 500000])

    if valid2:

        amt = valid2[-1]

        log.info(f'  Total={amt} (largest amount fallback)')

        return amt



    log.warning('  Could not extract total amount')



    log.warning("  ⚠ Could not extract total amount")

    return None





def _to_float(s) -> float | None:

    try: return float(str(s).replace(",","").strip())

    except: return None





def _sum_tax_amounts(matches: list) -> float | None:

    vals = [_to_float(m) for m in matches if _to_float(m) and _to_float(m) < 10000]

    return round(sum(vals[:2]), 2) if vals else None





def _regex_extract(text: str) -> dict:

    """Alias for backwards compatibility."""

    return _smart_extract(text)





def extract_structured_data(text: str) -> dict:

    """Alias — no longer calls Gemini."""

    return _smart_extract(text)















# ═══════════════════════════════════════════════════════════════════════════════

# BATCH PROCESSING

# ═══════════════════════════════════════════════════════════════════════════════



def process_multiple_bills(image_paths: list[str], **kwargs) -> list[dict]:

    """Process multiple bill images and return list of results."""

    results = []

    for i, path in enumerate(image_paths, 1):

        log.info(f"[{i}/{len(image_paths)}] {Path(path).name}")

        results.append(process_bill(path, **kwargs))

    return results





# ═══════════════════════════════════════════════════════════════════════════════

# FastAPI ENDPOINT WRAPPER

# ═══════════════════════════════════════════════════════════════════════════════



def get_ocr_router():

    """

    Returns a FastAPI APIRouter with /scan-bill endpoint.

    Import this in main.py:

        from ocr_engine import get_ocr_router

        app.include_router(get_ocr_router())

    """

    from fastapi import APIRouter, UploadFile, File, HTTPException, Query

    import shutil, tempfile, uuid



    router = APIRouter()



    @router.post("/scan-bill")

    async def scan_bill(

        file    : UploadFile = File(...),

        user_id : int        = Query(...),

    ):

        # Save uploaded file to temp dir

        ext      = Path(file.filename).suffix or ".jpg"

        fname    = f"{uuid.uuid4()}{ext}"

        tmp_dir  = Path(tempfile.gettempdir()) / "taxshield_bills"

        tmp_dir.mkdir(exist_ok=True)

        save_path = tmp_dir / fname



        try:

            with open(save_path, "wb") as buf:

                shutil.copyfileobj(file.file, buf)



            log.info(f"Bill saved: {fname}  user={user_id}  size={save_path.stat().st_size}")



            result = process_bill(str(save_path), use_vision=True, use_ocr=True)

            return {

                "status":   "success" if result.get("success") else "partial",

                "user_id":  user_id,

                "filename": fname,

                "data":     result,

            }



        except Exception as e:

            log.error(f"scan-bill error: {e}")

            raise HTTPException(status_code=500, detail=str(e))

        finally:

            try:

                save_path.unlink(missing_ok=True)

            except:

                pass



    return router





# ═══════════════════════════════════════════════════════════════════════════════

# CLI — TEST ON YOUR BILLS DIRECTLY

# ═══════════════════════════════════════════════════════════════════════════════



# Keep the module-level key synced to environment values loaded above.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)
