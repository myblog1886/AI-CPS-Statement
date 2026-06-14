from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.db import list_runs, get_run
from app.payroll_engine import MONTH_NAMES

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    try:
        runs = list_runs(limit=100)
    except Exception:
        runs = []
    return templates.TemplateResponse("history.html", {
        "request": request,
        "runs": runs,
        "month_names": MONTH_NAMES,
    })


@router.get("/run/{run_id}", response_class=HTMLResponse)
async def run_detail(request: Request, run_id: str):
    try:
        run = get_run(run_id)
    except Exception:
        run = None
    if not run:
        return HTMLResponse("<p>Run not found or DB unavailable.</p>", 404)
    return templates.TemplateResponse("run_detail.html", {
        "request": request,
        "run": run,
        "month_name": MONTH_NAMES.get(run["month"], ""),
    })
