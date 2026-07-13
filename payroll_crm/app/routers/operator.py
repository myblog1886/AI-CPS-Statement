from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime

from app.db import get_session
from app.models import Client, User, Run
from app.auth import role_required as _role_required

router = APIRouter(prefix="/operator", tags=["operator"])
BASE_DIR = Path(__file__).parent.parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

_require_operator = _role_required("operator")


def require_operator(request: Request, db: Session = Depends(get_session)):
    return _require_operator(request, db)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_session),
    user=Depends(require_operator),
):
    clients = db.query(Client).all()
    recent_runs = db.query(Run).order_by(Run.created_at.desc()).limit(20).all()

    now = datetime.utcnow()
    runs_this_month = db.query(Run).filter(
        Run.month == now.month,
        Run.year == now.year,
    ).count()

    return templates.TemplateResponse("operator_dashboard.html", {
        "request": request,
        "user": user,
        "clients": clients,
        "recent_runs": recent_runs,
        "runs_this_month": runs_this_month,
    })


@router.get("/clients", response_class=HTMLResponse)
def list_clients(
    request: Request,
    db: Session = Depends(get_session),
    user=Depends(require_operator),
):
    clients = db.query(Client).all()
    return templates.TemplateResponse("operator_clients.html", {
        "request": request,
        "user": user,
        "clients": clients,
    })


@router.post("/clients/add")
def add_client(
    request: Request,
    name: str = Form(...),
    gstin: str = Form(""),
    state: str = Form("MH"),
    epf_registered: bool = Form(False),
    esic_registered: bool = Form(False),
    db: Session = Depends(get_session),
    user=Depends(require_operator),
):
    client = Client(
        name=name,
        gstin=gstin,
        state=state,
        epf_registered=epf_registered,
        esic_registered=esic_registered,
    )
    db.add(client)
    db.commit()
    return RedirectResponse("/operator/clients", status_code=303)
