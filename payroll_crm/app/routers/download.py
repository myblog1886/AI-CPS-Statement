from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from pathlib import Path

from app.db import get_session
from app.models import Run, Output, Client
from app.auth import get_current_user as _get_current_user
from app.routers.client import _assert_run_access
from app.output.ecr import generate_ecr
from app.output.esic import generate_esic
from app.output.slips import generate_slips_zip
from app.output.bank import generate_bank_csv
from app.output.compliance_pdf import generate_compliance_pdf

router = APIRouter(prefix="/client", tags=["download"])
BASE_DIR = Path(__file__).parent.parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

OUTPUT_TYPES = ["ecr", "esic", "slips", "bank", "compliance"]


def get_current_user(request: Request, db: Session = Depends(get_session)):
    return _get_current_user(request, db)


@router.get("/download/{run_id}", response_class=HTMLResponse)
def download_page(
    request: Request,
    run_id: int,
    db: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    _assert_run_access(run, user)
    if run.status != "approved":
        raise HTTPException(403, "Run not approved yet")
    client = db.get(Client, run.client_id)
    return templates.TemplateResponse("download.html", {
        "request": request,
        "user": user,
        "run": run,
        "client": client,
    })


@router.get("/download/{run_id}/{output_type}")
def download_file(
    run_id: int,
    output_type: str,
    db: Session = Depends(get_session),
    user=Depends(get_current_user),
    request: Request = None,
):
    if output_type not in OUTPUT_TYPES:
        raise HTTPException(400, f"Unknown output type: {output_type}")
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    _assert_run_access(run, user)
    if run.status != "approved":
        raise HTTPException(403, "Run not approved yet")
    client = db.get(Client, run.client_id)

    payroll_results = json.loads(run.payroll_json or "[]")
    compliance_findings = json.loads(run.compliance_json or "[]")

    if output_type == "ecr":
        content = generate_ecr(payroll_results, run.month, run.year)
        media = "text/plain"
        filename = f"ECR_{run.month:02d}_{run.year}.txt"
    elif output_type == "esic":
        content = generate_esic(payroll_results, run.month, run.year)
        media = "text/csv"
        filename = f"ESIC_{run.month:02d}_{run.year}.csv"
    elif output_type == "slips":
        content = generate_slips_zip(payroll_results, run.month, run.year)
        media = "application/zip"
        filename = f"SalarySlips_{run.month:02d}_{run.year}.zip"
    elif output_type == "bank":
        content = generate_bank_csv(payroll_results, run.month, run.year)
        media = "text/csv"
        filename = f"BankTransfer_{run.month:02d}_{run.year}.csv"
    elif output_type == "compliance":
        content = generate_compliance_pdf(compliance_findings, client.name, run.month, run.year)
        media = "application/pdf"
        filename = f"ComplianceReport_{run.month:02d}_{run.year}.pdf"

    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/history", response_class=HTMLResponse)
def run_history(
    request: Request,
    client_id: int,
    db: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    runs = db.query(Run).filter(Run.client_id == client_id).order_by(Run.created_at.desc()).all()
    return templates.TemplateResponse("history.html", {
        "request": request,
        "user": user,
        "client": client,
        "runs": runs,
    })
