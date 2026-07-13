import sys
import os
sys.path.append("/Users/madhavibhat/payroll_v2")
sys.path.append("/Users/madhavibhat/cps-compliance-platform")

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

from app.db import engine
from app.models import Base

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Payroll CRM")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dev-secret"))

BASE_DIR = Path(__file__).parent.parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

from app.routers.auth_router import router as auth_router
from app.routers.run import router as run_router
from app.routers.operator import router as operator_router
from app.routers.client import router as client_router
from app.routers.download import router as download_router
app.include_router(auth_router)
app.include_router(run_router)
app.include_router(operator_router)
app.include_router(client_router)
app.include_router(download_router)

@app.exception_handler(401)
async def auth_redirect(request: Request, exc):
    return RedirectResponse("/login")


@app.get("/")
def root():
    return RedirectResponse("/login")
