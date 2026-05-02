"""
ocr.py – Bill scanning and structured data extraction using EasyOCR.

Supported input formats (file upload AND live camera canvas capture):
    JPEG, JPG, PNG, WEBP, BMP, TIFF, GIF (first frame)

Pipeline:
    1. Validate and normalise the image (convert to RGB JPEG if needed)
    2. Preprocess (grayscale → denoise → adaptive threshold → deskew)
    3. Run EasyOCR
    4. Extract amount, GST, date, vendor
    5. Score confidence and accuracy
"""

import re
import logging
from pathlib import Path
from typing import Optional, TypedDict

logger = logging.getLogger(__name__)


# ── Supported image MIME types ────────────────────────────────────────────────
SUPPORTED_IMAGE_TYPES = {
    "image/jpeg", "image/jpg", "image/png",
    "image/webp", "image/bmp", "image/tiff",
    "image/gif",  "image/x-png",
    "application/octet-stream",   # canvas toBlob fallback in some browsers
}

# ── OCR result schema ─────────────────────────────────────────────────────────
class BillData(TypedDict):
    raw_text:       str
    amount:         Optional[float]
    gst:            float
    date:           Optional[str]
    vendor:         str
    ocr_confidence: float
    accuracy_score: float
    source:         str     # "upload" or "live_camera"

# ── Amount / date patterns ────────────────────────────────────────────────────
AMOUNT_PATTERN = re.compile(r"[\d,]+(?:\.\d{1,2})?")
DATE_PATTERN   = re.compile(r"\b\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b")

TOTAL_KEYWORDS = [
    "net payable", "net amount", "grand total",
    "total amount", "amount payable", "bill amount",
    "total", "amount",
]


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def extract_bill_data(image_path: str, source: str = "upload") -> BillData:
    """
    Run the full OCR pipeline on a bill image.

    Args:
        image_path: Path to the saved image file (any supported format).
        source:     "upload" or "live_camera" — stored for frontend display.

    Returns:
        BillData dict with all extracted fields and quality scores.
    """
    path = Path(image_path)
    if not path.exists():
        logger.error("Image not found: %s", image_path)
        return _empty_result(source)

    logger.info("Processing bill image: %s  size=%d bytes  source=%s",
                path.name, path.stat().st_size, source)

    # ── Step 1: Normalise to a clean image array ───────────────────────────────
    img_array = _load_and_normalise(path)
    if img_array is None:
        return _empty_result(source)

    # ── Step 2: Preprocess ─────────────────────────────────────────────────────
    processed = _preprocess(img_array)

    # ── Step 3: OCR ───────────────────────────────────────────────────────────
    ocr_result = _run_ocr(processed)
    if ocr_result is None:
        return _empty_result(source)

    # ── Step 4: Build raw text ─────────────────────────────────────────────────
    raw_text = "\n".join(text for (_, text, _) in ocr_result).strip()
    logger.debug("OCR raw text:\n%s", raw_text)

    # ── Step 5: Extract fields ─────────────────────────────────────────────────
    amount = _extract_amount(raw_text)
    gst    = _extract_gst(raw_text, amount)
    date   = _extract_date(raw_text)
    vendor = _extract_vendor(raw_text)

    # ── Step 6: Quality scores ─────────────────────────────────────────────────
    confidence   = _ocr_confidence(ocr_result)
    amount_score = _validate_amount(amount)
    accuracy     = round(confidence * 0.6 + amount_score * 0.4, 2)

    logger.info("Bill parsed — vendor=%s  amount=₹%s  gst=₹%s  confidence=%.1f%%  source=%s",
                vendor, amount, gst, confidence, source)

    return BillData(
        raw_text=raw_text,
        amount=amount,
        gst=gst,
        date=date,
        vendor=vendor,
        ocr_confidence=round(confidence, 2),
        accuracy_score=accuracy,
        source=source,
    )


def is_supported_image(content_type: str) -> bool:
    """Return True if the MIME type is a supported image format."""
    ct = content_type.lower().split(";")[0].strip()
    return ct in SUPPORTED_IMAGE_TYPES or ct.startswith("image/")


# ══════════════════════════════════════════════════════════════════════════════
# IMAGE LOADING & NORMALISATION
# ══════════════════════════════════════════════════════════════════════════════

def _load_and_normalise(path: Path):
    """
    Load the image with Pillow (handles all common formats including WEBP, GIF)
    and convert to a numpy array for OpenCV/EasyOCR.

    Falls back to direct cv2.imread if Pillow is unavailable.
    Returns a numpy array or None on failure.
    """
    import numpy as np

    # ── Try Pillow first (best format support) ────────────────────────────────
    try:
        from PIL import Image
        img_pil = Image.open(str(path))

        # Take first frame of animated GIF
        if getattr(img_pil, "is_animated", False):
            img_pil.seek(0)

        # Convert palette / RGBA / greyscale → RGB
        if img_pil.mode not in ("RGB", "L"):
            img_pil = img_pil.convert("RGB")

        img_array = np.array(img_pil)

        # Pillow gives RGB — convert to BGR for OpenCV
        if len(img_array.shape) == 3 and img_array.shape[2] == 3:
            import cv2
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        logger.debug("Loaded via Pillow: %s  shape=%s", path.name, img_array.shape)
        return img_array

    except ImportError:
        pass   # Fall through to cv2
    except Exception as exc:
        logger.warning("Pillow failed to load %s: %s — trying cv2", path.name, exc)

    # ── Fallback: OpenCV direct read ──────────────────────────────────────────
    try:
        import cv2
        img = cv2.imread(str(path))
        if img is None:
            raise ValueError("cv2.imread returned None")
        logger.debug("Loaded via cv2: %s  shape=%s", path.name, img.shape)
        return img
    except Exception as exc:
        logger.error("Failed to load image %s: %s", path.name, exc)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PREPROCESSING
# ══════════════════════════════════════════════════════════════════════════════

def _preprocess(img):
    """
    Full preprocessing pipeline:
    resize → grayscale → denoise → adaptive threshold → deskew.
    Falls back gracefully at each step if cv2 is unavailable.
    """
    try:
        import cv2
        import numpy as np

        # Resize if too large
        h, w = img.shape[:2]
        if max(h, w) > 2000:
            scale = 2000 / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        # Grayscale
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img

        # Denoise
        denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)

        # Adaptive threshold — handles shadows / uneven lighting in phone photos
        thresh = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=31, C=10,
        )

        # Deskew
        return _deskew(thresh)

    except Exception as exc:
        logger.warning("Preprocessing failed (%s) — using raw image", exc)
        return img


def _deskew(image):
    """Correct skew if angle > 1°."""
    try:
        import cv2
        import numpy as np
        coords = np.column_stack(np.where(image > 0))
        if len(coords) < 5:
            return image
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        if abs(angle) < 1.0:
            return image
        h, w = image.shape[:2]
        M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
        return cv2.warpAffine(image, M, (w, h),
                              flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)
    except Exception:
        return image


# ══════════════════════════════════════════════════════════════════════════════
# OCR
# ══════════════════════════════════════════════════════════════════════════════

def _run_ocr(image) -> Optional[list]:
    """Run EasyOCR and return raw result list or None on failure."""
    try:
        import easyocr
        reader = easyocr.Reader(["en"], verbose=False)
        result = reader.readtext(image)
        logger.debug("EasyOCR detected %d text regions", len(result))
        return result
    except ImportError:
        logger.error("easyocr not installed. Run: pip install easyocr")
        return None
    except Exception as exc:
        logger.exception("EasyOCR failed: %s", exc)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# FIELD EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def _extract_amount(text: str) -> Optional[float]:
    """Find the bill total — scans bottom 10 lines first, then full text."""
    lines = text.lower().split("\n")
    bottom = lines[-10:] if len(lines) > 10 else lines

    for line in reversed(bottom):
        for keyword in TOTAL_KEYWORDS:
            if keyword in line:
                val = _largest_amount_in(line)
                if val:
                    return val

    return _largest_amount_in(text)


def _largest_amount_in(text: str) -> Optional[float]:
    candidates = []
    for raw in AMOUNT_PATTERN.findall(text):
        try:
            v = float(raw.replace(",", ""))
            if 1.0 <= v <= 1_000_000:
                candidates.append(v)
        except ValueError:
            continue
    return max(candidates) if candidates else None


def _extract_gst(text: str, total: Optional[float]) -> float:
    """Find GST from explicit GST/CGST/SGST lines; estimate 18% if not found."""
    for line in text.lower().split("\n"):
        if any(tag in line for tag in ("gst", "cgst", "sgst", "igst", "tax")):
            val = _largest_amount_in(line)
            if val and (total is None or val < total):
                return val
    # Back-calculate 18% GST from GST-inclusive total
    if total:
        return round(total * 18 / 118, 2)
    return 0.0


def _extract_date(text: str) -> Optional[str]:
    m = DATE_PATTERN.search(text)
    return m.group() if m else None


def _extract_vendor(text: str) -> str:
    """Return the first non-numeric line from the top of the bill."""
    for line in text.split("\n")[:6]:
        line = line.strip()
        if len(line) >= 3 and not any(c.isdigit() for c in line):
            return line
    return "Unknown Vendor"


# ══════════════════════════════════════════════════════════════════════════════
# QUALITY SCORING
# ══════════════════════════════════════════════════════════════════════════════

def _ocr_confidence(result: list) -> float:
    if not result:
        return 0.0
    scores = [r[2] for r in result if len(r) >= 3]
    return (sum(scores) / len(scores)) * 100 if scores else 0.0


def _validate_amount(amount: Optional[float]) -> float:
    return 100.0 if (amount and 0 < amount <= 1_000_000) else 0.0


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _empty_result(source: str) -> BillData:
    return BillData(
        raw_text="", amount=None, gst=0.0,
        date=None, vendor="Unknown Vendor",
        ocr_confidence=0.0, accuracy_score=0.0,
        source=source,
    )
