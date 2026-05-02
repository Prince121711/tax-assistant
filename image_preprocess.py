"""
utils/image_preprocess.py – Image preprocessing pipeline for OCR quality improvement.

Pipeline:
    1. Load and validate the image
    2. Convert to grayscale
    3. Denoise
    4. Adaptive threshold (handles uneven lighting common in bill photos)
    5. Deskew (straighten tilted images)

Returns the processed image array ready for EasyOCR.
"""

import logging
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)


def preprocess_image(path: str) -> np.ndarray:
    """
    Load and preprocess a bill image for improved OCR accuracy.

    Args:
        path: Absolute or relative path to the image file.

    Returns:
        Processed grayscale numpy array.

    Raises:
        ValueError: If the path is invalid or the image cannot be loaded.
    """
    try:
        import cv2
    except ImportError:
        raise ImportError("opencv-python is required. Run: pip install opencv-python")

    if not isinstance(path, (str, Path)):
        raise ValueError(f"Expected a file path string, got {type(path)}")

    image_path = Path(path)
    if not image_path.exists():
        raise ValueError(f"Image file not found: {path}")

    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"cv2 could not read the image (corrupt or unsupported format): {path}")

    logger.debug("Preprocessing image: %s  shape=%s", image_path.name, img.shape)

    # ── Step 1: Resize if very large (speeds up OCR without losing detail) ────
    img = _resize_if_large(img, max_dimension=2000)

    # ── Step 2: Grayscale ─────────────────────────────────────────────────────
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # ── Step 3: Denoise ───────────────────────────────────────────────────────
    denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)

    # ── Step 4: Adaptive threshold (handles shadows / uneven lighting) ────────
    thresh = cv2.adaptiveThreshold(
        denoised,
        maxValue=255,
        adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresholdType=cv2.THRESH_BINARY,
        blockSize=31,
        C=10,
    )

    # ── Step 5: Deskew ────────────────────────────────────────────────────────
    deskewed = _deskew(thresh)

    logger.debug("Preprocessing complete for %s", image_path.name)
    return deskewed


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resize_if_large(img: np.ndarray, max_dimension: int = 2000) -> np.ndarray:
    """Downscale image if either dimension exceeds max_dimension."""
    try:
        import cv2
    except ImportError:
        return img

    h, w = img.shape[:2]
    if max(h, w) <= max_dimension:
        return img

    scale = max_dimension / max(h, w)
    new_w = int(w * scale)
    new_h = int(h * scale)
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    logger.debug("Resized from (%d×%d) to (%d×%d)", w, h, new_w, new_h)
    return resized


def _deskew(image: np.ndarray) -> np.ndarray:
    """
    Correct skew in a thresholded image using the minimum area rectangle method.
    Skips correction if the detected angle is within ±1° (already straight).
    """
    try:
        import cv2
    except ImportError:
        return image

    coords = np.column_stack(np.where(image > 0))
    if len(coords) < 5:
        return image  # Not enough content to detect skew

    angle = cv2.minAreaRect(coords)[-1]

    # cv2.minAreaRect returns angles in [-90, 0); normalise to [-45, 45)
    if angle < -45:
        angle = 90 + angle

    if abs(angle) < 1.0:
        return image  # Already straight — skip expensive rotation

    (h, w) = image.shape[:2]
    centre = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(centre, angle, 1.0)
    rotated = cv2.warpAffine(
        image, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )

    logger.debug("Deskewed by %.2f°", angle)
    return rotated
