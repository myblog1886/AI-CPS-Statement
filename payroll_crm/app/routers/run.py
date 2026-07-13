import anthropic
import json
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.auth import get_current_user as _get_current_user
from app.db import get_session
from app.engines.compliance import run_compliance
from app.engines.payroll import run_payroll
from app.ingest.structured import parse_structured
from app.ingest.unstructured import parse_unstructured
from app.models import Client, Run, RunFile

router = APIRouter(prefix="/run", tags=["run"])


def get_current_user(request: Request, db: Session = Depends(get_session)):
    return _get_current_user(request, db)

STRUCTURED_EXTS = {".csv", ".xlsx", ".xls"}
UNSTRUCTURED_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".docx", ".txt"}

TEXT_EDIT_PROMPT = """You are a payroll data assistant. Given the current employee list (JSON) and a natural language instruction, return a modified JSON array applying the instruction.
Return ONLY the modified JSON array. No explanation."""


def _ingest(path: Path) -> list[dict]:
    if path.suffix.lower() in STRUCTURED_EXTS:
        return parse_structured(path)
    return parse_unstructured(path)


def orchestrate(
    client_id: int,
    employees: list[dict],
    month: int,
    year: int,
    db: Session,
    parent_run_id: int | None = None,
) -> Run:
    """Run payroll + compliance and persist a Run record. Returns the Run."""
    client = db.get(Client, client_id)
    if not client:
        raise ValueError(f"Client {client_id} not found")

    payroll_results = run_payroll(employees, month, year)
    compliance_findings = run_compliance(payroll_results, client)

    run = Run(
        client_id=client_id,
        month=month,
        year=year,
        payroll_json=json.dumps(payroll_results),
        compliance_json=json.dumps(compliance_findings),
        status="draft",
        parent_run_id=parent_run_id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def apply_text_edit(employees: list[dict], instruction: str) -> list[dict]:
    """Apply a natural language edit instruction to the employee list via Claude."""
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        raise ValueError("CLAUDE_API_KEY not set")
    client = anthropic.Anthropic(api_key=api_key)
    prompt = f"{TEXT_EDIT_PROMPT}\n\nCurrent data:\n{json.dumps(employees, indent=2)}\n\nInstruction: {instruction}"
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        result = json.loads(raw.strip())
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}")
    if not isinstance(result, list):
        raise ValueError("Claude did not return a JSON array")
    return result


@router.post("/upload")
async def upload_and_run(
    client_id: int = Form(...),
    month: int = Form(...),
    year: int = Form(...),
    file: UploadFile = File(...),
    parent_run_id: int | None = Form(None),
    db: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    suffix = Path(file.filename).suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)
    try:
        employees = _ingest(tmp_path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        tmp_path.unlink(missing_ok=True)

    run = orchestrate(client_id, employees, month, year, db, parent_run_id)
    # Store uploaded file reference
    rf = RunFile(run_id=run.id, filename=file.filename, file_type=suffix.lstrip("."))
    db.add(rf)
    db.commit()
    return {"run_id": run.id}


@router.post("/edit")
def text_edit_and_run(
    run_id: int = Form(...),
    instruction: str = Form(...),
    db: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    parent = db.get(Run, run_id)
    if not parent:
        raise HTTPException(404, "Run not found")
    from app.routers.client import _extract_employee_inputs
    raw_employees = _extract_employee_inputs(json.loads(parent.payroll_json or "[]"))
    try:
        edited = apply_text_edit(raw_employees, instruction)
    except ValueError as e:
        raise HTTPException(400, str(e))
    run = orchestrate(parent.client_id, edited, parent.month, parent.year, db, run_id)
    return {"run_id": run.id}
