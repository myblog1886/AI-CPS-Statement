import json
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user as _get_current_user
from app.db import get_session
from app.models import Client, EditRequest, Run
from app.routers.run import STRUCTURED_EXTS, _ingest, apply_text_edit, orchestrate

router = APIRouter(prefix="/client", tags=["client"])
BASE_DIR = Path(__file__).parent.parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

EMPLOYEE_INPUT_FIELDS = [
    "emp_id", "name", "uan", "pf_number", "esic_number", "basic", "da", "hra",
    "other_allowances", "days_in_month", "days_worked", "advance_deduction",
    "bank_account", "ifsc_code", "designation", "department",
]


def _extract_employee_inputs(payroll_results: list[dict]) -> list[dict]:
    return [
        {
            f: r.get(
                f,
                0 if f in ["basic", "da", "hra", "other_allowances", "advance_deduction"]
                else (30 if f in ["days_in_month", "days_worked"] else "")
            )
            for f in EMPLOYEE_INPUT_FIELDS
        }
        for r in payroll_results
    ]


def _assert_run_access(run: Run, user):
    if user.role == "operator":
        return
    if run.client_id != user.client_id:
        raise HTTPException(403, "Access denied")


def get_current_user(request: Request, db: Session = Depends(get_session)):
    return _get_current_user(request, db)


@router.get("/upload", response_class=HTMLResponse)
def upload_form(
    request: Request,
    client_id: int,
    db: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    return templates.TemplateResponse("upload.html", {
        "request": request,
        "user": user,
        "client": client,
    })


@router.post("/upload")
async def upload_file(
    request: Request,
    client_id: int = Form(...),
    month: int = Form(...),
    year: int = Form(...),
    parent_run_id: int | None = Form(None),
    file: UploadFile = File(...),
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
    return RedirectResponse(f"/client/review/{run.id}", status_code=303)


@router.get("/review/{run_id}", response_class=HTMLResponse)
def review(
    request: Request,
    run_id: int,
    db: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    _assert_run_access(run, user)
    payroll_results = json.loads(run.payroll_json or "[]")
    compliance_findings = json.loads(run.compliance_json or "[]")
    total_gross = sum(r.get("gross_salary", 0) for r in payroll_results)
    total_net = sum(r.get("net_salary", 0) for r in payroll_results)
    total_pf = sum(r.get("employer_pf", 0) for r in payroll_results)
    total_esic = sum(r.get("employer_esic", 0) for r in payroll_results)
    fail_count = sum(1 for f in compliance_findings if f.get("status") == "fail")
    partial_count = sum(1 for f in compliance_findings if f.get("status") == "partial")
    can_approve = fail_count == 0
    return templates.TemplateResponse("review.html", {
        "request": request,
        "user": user,
        "run": run,
        "payroll_results": payroll_results,
        "compliance_findings": compliance_findings,
        "total_gross": total_gross,
        "total_net": total_net,
        "total_pf": total_pf,
        "total_esic": total_esic,
        "fail_count": fail_count,
        "partial_count": partial_count,
        "can_approve": can_approve,
    })


@router.post("/approve/{run_id}")
def approve_run(
    run_id: int,
    db: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    _assert_run_access(run, user)
    compliance_findings = json.loads(run.compliance_json or "[]")
    fail_count = sum(1 for f in compliance_findings if f.get("status") == "fail")
    if fail_count > 0:
        raise HTTPException(400, "Cannot approve run with failing compliance checks")
    run.status = "approved"
    db.commit()
    return RedirectResponse(f"/client/download/{run_id}", status_code=303)


@router.post("/edit/text/{run_id}")
def text_edit(
    run_id: int,
    instruction: str = Form(...),
    db: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    parent = db.get(Run, run_id)
    if not parent:
        raise HTTPException(404, "Run not found")
    _assert_run_access(parent, user)
    raw_employees = _extract_employee_inputs(json.loads(parent.payroll_json or "[]"))
    try:
        edited = apply_text_edit(raw_employees, instruction)
    except ValueError as e:
        raise HTTPException(400, str(e))
    er = EditRequest(run_id=run_id, type="text", content=instruction)
    db.add(er)
    run = orchestrate(parent.client_id, edited, parent.month, parent.year, db, run_id)
    db.commit()
    return RedirectResponse(f"/client/review/{run.id}", status_code=303)
