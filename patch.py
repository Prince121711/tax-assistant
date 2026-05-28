import ast


def main():
    with open('ocr_engine.py', 'rb') as f:
        raw = f.read()

    text = raw.decode('utf-8', errors='replace')
    with open('ocr_engine.py', 'w', encoding='utf-8') as f:
        f.write(text)

    with open('ocr_engine.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    pb_line = next(i for i, l in enumerate(lines) if 'def process_bill(' in l)
    smart_line = next(i for i, l in enumerate(lines) if 'structured = _smart_extract(result' in l)

    enhance = [
        '
',
        'def _gemini_enhance(ocr_text, api_key):
',
        '    import requests as rq, json as js
',
        '    url = _resolve_gemini_url()
',
        '    if not url: return {}
',
        '    p = "From this Indian bill OCR text, return ONLY this JSON (no markdown):
"
',
        '    p += "{\"vendor_name\": \"shop name in English\", \"total_amount\": 0, \"date\": \"YYYY-MM-DD\"}
"
',
        '    p += "Translate Tamil shop names to English.

OCR TEXT:
" + ocr_text[:1500]
',
        '    try:
',
        '        r = rq.post(f"{url}?key={api_key}",
',
        '            json={"contents":[{"parts":[{"text":p}]}],"generationConfig":{"temperature":0,"maxOutputTokens":200}},
',
        '            timeout=15)
',
        '        if r.status_code == 429: return {}
',
        '        r.raise_for_status()
',
        '        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
',
        '        raw = raw.strip().replace("`json", "").replace("`", "").strip()
',
        '        return js.loads(raw)
',
        '    except Exception:
',
        '        return {}
',
        '
',
    ]

    lines[pb_line:pb_line] = enhance
    smart_line += len(enhance)

    step3b = [
        '
',
        '        api_key = _get_api_key()
',
        '        if api_key and result.get("ocr_text"):
',
        '            enh = _gemini_enhance(result["ocr_text"], api_key)
',
        '            if enh.get("vendor_name"): structured["vendor_name"] = enh["vendor_name"]
',
        '            if enh.get("total_amount") and not structured.get("total_amount"): structured["total_amount"] = enh["total_amount"]
',
        '            if enh.get("date") and not structured.get("date"): structured["date"] = enh["date"]
',
    ]

    lines[smart_line + 1:smart_line + 1] = step3b

    with open('ocr_engine.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)

    try:
        ast.parse(''.join(lines))
        print('Updated ocr_engine.py successfully.')
    except SyntaxError as e:
        print('Error:', e)
        raise


if __name__ == '__main__':
    main()
