import io
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()

from app.routers import payroll, compare, history

app = FastAPI(title="CPS LLP — India Payroll Copilot v2")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(payroll.router)
app.include_router(compare.router)
app.include_router(history.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/sample-csv")
async def sample_csv():
    with open("sample_data.csv", "rb") as f:
        return StreamingResponse(
            io.BytesIO(f.read()),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="sample_payroll.csv"'},
        )
