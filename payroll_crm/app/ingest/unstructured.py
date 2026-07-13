import os
import json
import base64
from pathlib import Path
import anthropic

EXTRACTION_PROMPT = """Extract payroll data from the provided document.
Return ONLY a valid JSON array. Each element must be:
{
  "emp_id": "string or null",
  "name": "string",
  "uan": "string or null",
  "pf_number": "string or null",
  "esic_number": "string or null",
  "basic": number,
  "da": number,
  "hra": number,
  "other_allowances": number,
  "days_in_month": number,
  "days_worked": number,
  "advance_deduction": number,
  "bank_account": "string or null",
  "ifsc_code": "string or null",
  "designation": "string or null",
  "department": "string or null"
}
Use 0 for unknown numeric values. Return [] if no employee data found. No explanation, just the JSON array."""


def _read_file_content(path: Path) -> tuple[str, object]:
    suffix = path.suffix.lower()
    if suffix in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        media_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                     ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
        with open(path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode()
        return "image", (media_map[suffix], data)
    elif suffix == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
            return "text", text
        except ImportError:
            with open(path, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode()
            return "image", ("application/pdf", data)
    else:
        with open(path, "r", errors="ignore") as f:
            return "text", f.read()


def _parse_json_response(raw: str) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        result = json.loads(raw.strip())
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\nRaw: {raw[:300]}")
    if not isinstance(result, list):
        raise ValueError("Claude did not return a JSON array")
    return result


def _normalise_employee(e: dict) -> dict:
    return {
        "emp_id": str(e.get("emp_id") or ""),
        "name": str(e.get("name") or ""),
        "uan": str(e.get("uan") or ""),
        "pf_number": str(e.get("pf_number") or ""),
        "esic_number": str(e.get("esic_number") or ""),
        "basic": float(e.get("basic") or 0),
        "da": float(e.get("da") or 0),
        "hra": float(e.get("hra") or 0),
        "other_allowances": float(e.get("other_allowances") or 0),
        "days_in_month": int(e.get("days_in_month") or 30),
        "days_worked": int(e.get("days_worked") or 0),
        "advance_deduction": float(e.get("advance_deduction") or 0),
        "bank_account": str(e.get("bank_account") or ""),
        "ifsc_code": str(e.get("ifsc_code") or ""),
        "designation": str(e.get("designation") or ""),
        "department": str(e.get("department") or ""),
    }


def parse_unstructured(path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        raise ValueError(f"File not found: {path}")

    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        raise ValueError("CLAUDE_API_KEY not set in environment")

    client = anthropic.Anthropic(api_key=api_key)
    content_type, content = _read_file_content(path)

    if content_type == "image":
        media_type, data = content
        message_content = [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
            {"type": "text", "text": EXTRACTION_PROMPT},
        ]
    else:
        message_content = [{"type": "text", "text": f"{EXTRACTION_PROMPT}\n\nDocument:\n{content}"}]

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": message_content}],
    )

    employees = _parse_json_response(response.content[0].text)
    return [_normalise_employee(e) for e in employees if str(e.get("name", "")).strip()]
