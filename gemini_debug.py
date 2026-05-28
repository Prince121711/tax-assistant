import os
import json
import base64
import requests
from ocr_engine import _get_api_key, _resolve_gemini_url


def main():
    img = os.path.join(os.getcwd(), "uploads", "bdaae966-c5b7-44f9-8e1e-7abf68473e92.jpg")
    api_key = _get_api_key()
    url = _resolve_gemini_url()
    if not url or not api_key:
        raise RuntimeError("Gemini API URL or key not available.")

    with open(img, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    media_type = "image/jpeg"
    body = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": media_type, "data": image_data}},
                {"text": "Hello"}
            ]
        }],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 2048,
            "response_mime_type": "application/json",
        },
    }

    session = requests.Session()
    session.trust_env = False
    response = session.post(f"{url}?key={api_key}", json=body, timeout=90)
    response.raise_for_status()

    try:
        payload = response.json()
    except json.JSONDecodeError as err:
        raise RuntimeError("Failed to parse Gemini response") from err

    print(json.dumps(payload, indent=2)[:2000])


if __name__ == "__main__":
    main()
