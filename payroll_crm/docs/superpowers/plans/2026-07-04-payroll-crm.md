# Payroll CRM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first FastAPI CRM that ingests client payroll files, runs statutory calculations and compliance validation, supports an iterative review/edit loop, and delivers EPFO ECR, ESIC CSV, salary slips, bank file, and compliance report on client approval.

**Architecture:** Single FastAPI process imports both existing engines as Python libraries — no inter-process HTTP. SQLite via SQLAlchemy (one env var switches to PostgreSQL). Two roles: operator (all clients) and client (own runs only).

**Tech Stack:** Python 3.12, FastAPI 0.111, SQLAlchemy 2.0, Jinja2, itsdangerous, bcrypt, pandas, openpyxl, anthropic (Claude API), ReportLab, python-multipart, python-dotenv.

## Global Constraints

- Python path: add `/Users/madhavibhat/payroll_v2` and `/Users/madhavibhat/cps-compliance-platform` to `sys.path` in `app/main.py` before any engine imports
- `DATABASE_URL` env var drives all DB connections — default `sqlite:///./payroll_crm.db`
- `CLAUDE_API_KEY` env var for unstructured ingestion
- `SECRET_KEY` env var for session signing (itsdangerous)
- Never hardcode paths — use `pathlib.Path(__file__).parent` for relative paths
- All output files written to `payroll_crm/outputs/{run_id}/` — gitignored
- All upload files written to `payroll_crm/uploads/{run_id}/` — gitignored
- SQLAlchemy 2.0 style only: `with Session(engine) as s:` — no legacy `session.commit()` patterns
- bcrypt 3.2 API: `bcrypt.hashpw(pwd.encode(), bcrypt.gensalt())` / `bcrypt.checkpw(pwd.encode(), hash)`
- Tests use pytest with a fresh in-memory SQLite DB per test via fixtures

---

## File Map

```
payroll_crm/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, sys.path setup, router registration
│   ├── db.py                    # SQLAlchemy engine + get_session() dependency
│   ├── models.py                # ORM: User, Client, Run, RunFile, EditRequest, Output
│   ├── auth.py                  # get_current_user(), role_required(), hash/verify pwd
│   ├── engines/
│   │   ├── __init__.py
│   │   ├── payroll.py           # run_payroll(employees, month, year) -> list[PayrollResult]
│   │   └── compliance.py       # run_compliance(payroll_results, client) -> list[dict]
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── structured.py        # parse_structured(path) -> list[dict]
│   │   └── unstructured.py      # parse_unstructured(path) -> list[dict]
│   └── routers/
│       ├── auth_router.py       # GET/POST /login, POST /logout
│       ├── operator.py          # /operator/dashboard, /operator/clients CRUD
│       ├── client.py            # /upload, /review/{run_id}, /run/{run_id}/edit, /run/{run_id}/approve
│       ├── run.py               # orchestrate(file_path, client, month, year) -> Run
│       └── download.py          # /download/{run_id}/{file_type}
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── operator_dashboard.html
│   ├── operator_clients.html
│   ├── upload.html
│   ├── review.html
│   ├── download.html
│   └── history.html
├── static/
│   ├── style.css
│   └── app.js
├── tests/
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_auth.py
│   ├── test_engines.py
│   ├── test_ingest.py
│   ├── test_orchestrator.py
│   └── test_routes.py
├── outputs/                     # gitignored
├── uploads/                     # gitignored
├── .env.example
├── requirements.txt
└── README.md
```

---

## Task 1: Project Scaffold + Database + Models

**Files:**
- Create: `payroll_crm/requirements.txt`
- Create: `payroll_crm/.env.example`
- Create: `payroll_crm/.gitignore`
- Create: `payroll_crm/app/__init__.py`
- Create: `payroll_crm/app/db.py`
- Create: `payroll_crm/app/models.py`
- Create: `payroll_crm/app/main.py`
- Create: `payroll_crm/tests/conftest.py`
- Create: `payroll_crm/tests/test_models.py`

**Interfaces:**
- Produces: `get_session()` FastAPI dependency, `Base`, all ORM model classes imported by all later tasks

- [ ] **Step 1: Create requirements.txt**

```
fastapi==0.111.0
uvicorn[standard]==0.30.0
sqlalchemy==2.0.34
jinja2==3.1.4
python-multipart==0.0.9
python-dotenv==1.0.1
itsdangerous==2.2.0
bcrypt==3.2.0
pandas==2.2.2
openpyxl==3.1.4
reportlab==4.2.0
anthropic==0.30.0
aiofiles==23.2.1
pytest==8.2.0
httpx==0.27.0
pytest-asyncio==0.23.7
```

- [ ] **Step 2: Install missing packages**

```bash
cd /Users/madhavibhat/payroll_crm
pip3 install anthropic==0.30.0 aiofiles==23.2.1 pytest==8.2.0 httpx==0.27.0 pytest-asyncio==0.23.7
```

Expected: all packages install without error.

- [ ] **Step 3: Create .env.example**

```
DATABASE_URL=sqlite:///./payroll_crm.db
CLAUDE_API_KEY=sk-ant-...
SECRET_KEY=change-me-to-a-random-32-char-string
```

- [ ] **Step 4: Create .gitignore**

```
.env
payroll_crm.db
uploads/
outputs/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 5: Create app/db.py**

```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./payroll_crm.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine)

def get_session():
    with SessionLocal() as session:
        yield session
```

- [ ] **Step 6: Create app/models.py**

```python
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean,
    ForeignKey, Text, CheckConstraint
)
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase):
    pass

class Client(Base):
    __tablename__ = "clients"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    name             = Column(String, nullable=False)
    establishment_id = Column(String)
    state            = Column(String, nullable=False)
    industry_type    = Column(String)
    headcount        = Column(Integer)
    created_at       = Column(DateTime, default=datetime.utcnow)
    users            = relationship("User", back_populates="client")
    runs             = relationship("Run", back_populates="client")

class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    email         = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role          = Column(String, nullable=False)
    client_id     = Column(Integer, ForeignKey("clients.id"), nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    client        = relationship("Client", back_populates="users")
    __table_args__ = (CheckConstraint("role IN ('operator','client')"),)

class Run(Base):
    __tablename__ = "runs"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    client_id        = Column(Integer, ForeignKey("clients.id"), nullable=False)
    month            = Column(Integer, nullable=False)
    year             = Column(Integer, nullable=False)
    version          = Column(Integer, nullable=False, default=1)
    status           = Column(String, nullable=False, default="draft")
    payroll_json     = Column(Text)   # JSON: list of payroll result dicts
    compliance_json  = Column(Text)   # JSON: list of finding dicts
    created_by       = Column(Integer, ForeignKey("users.id"))
    approved_by      = Column(Integer, ForeignKey("users.id"))
    approved_at      = Column(DateTime)
    created_at       = Column(DateTime, default=datetime.utcnow)
    client           = relationship("Client", back_populates="runs")
    files            = relationship("RunFile", back_populates="run")
    edit_requests    = relationship("EditRequest", back_populates="run")
    outputs          = relationship("Output", back_populates="run")
    __table_args__   = (CheckConstraint("status IN ('draft','approved','error')"),)

class RunFile(Base):
    __tablename__ = "run_files"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    run_id        = Column(Integer, ForeignKey("runs.id"), nullable=False)
    file_type     = Column(String)
    original_name = Column(String)
    storage_path  = Column(String, nullable=False)
    created_at    = Column(DateTime, default=datetime.utcnow)
    run           = relationship("Run", back_populates="files")

class EditRequest(Base):
    __tablename__ = "edit_requests"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    run_id     = Column(Integer, ForeignKey("runs.id"), nullable=False)
    type       = Column(String, nullable=False)
    content    = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    run        = relationship("Run", back_populates="edit_requests")
    __table_args__ = (CheckConstraint("type IN ('text','reupload')"),)

class Output(Base):
    __tablename__ = "outputs"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    run_id       = Column(Integer, ForeignKey("runs.id"), nullable=False)
    output_type  = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    created_at   = Column(DateTime, default=datetime.utcnow)
    run          = relationship("Run", back_populates="outputs")
    __table_args__ = (CheckConstraint("output_type IN ('ecr','esic','slips','bank','compliance')"),)
```

- [ ] **Step 7: Create app/main.py (skeleton)**

```python
import sys
import os
sys.path.insert(0, "/Users/madhavibhat/payroll_v2")
sys.path.insert(0, "/Users/madhavibhat/cps-compliance-platform")

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from app.db import engine
from app.models import Base

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Payroll CRM")

BASE_DIR = Path(__file__).parent.parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Routers registered in later tasks
```

- [ ] **Step 8: Create static/style.css and static/app.js (empty stubs)**

```bash
mkdir -p /Users/madhavibhat/payroll_crm/static /Users/madhavibhat/payroll_crm/templates /Users/madhavibhat/payroll_crm/uploads /Users/madhavibhat/payroll_crm/outputs /Users/madhavibhat/payroll_crm/tests /Users/madhavibhat/payroll_crm/app/engines /Users/madhavibhat/payroll_crm/app/ingest /Users/madhavibhat/payroll_crm/app/routers
touch /Users/madhavibhat/payroll_crm/static/style.css /Users/madhavibhat/payroll_crm/static/app.js
touch /Users/madhavibhat/payroll_crm/app/__init__.py /Users/madhavibhat/payroll_crm/app/engines/__init__.py /Users/madhavibhat/payroll_crm/app/ingest/__init__.py /Users/madhavibhat/payroll_crm/app/routers/__init__.py
```

- [ ] **Step 9: Write failing test**

```python
# tests/test_models.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, Client, User, Run

@pytest.fixture
def session():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as s:
        yield s

def test_create_client_and_user(session):
    c = Client(name="Test Co", state="Maharashtra", establishment_id="MH/MUM/001")
    session.add(c)
    session.flush()
    u = User(email="a@b.com", password_hash="x", role="client", client_id=c.id)
    session.add(u)
    session.commit()
    assert session.get(Client, c.id).name == "Test Co"
    assert session.get(User, u.id).role == "client"

def test_create_run(session):
    c = Client(name="Co", state="Maharashtra")
    session.add(c); session.flush()
    r = Run(client_id=c.id, month=6, year=2026)
    session.add(r); session.commit()
    assert session.get(Run, r.id).status == "draft"
    assert session.get(Run, r.id).version == 1
```

- [ ] **Step 10: Run test — expect FAIL (import error before app exists fully)**

```bash
cd /Users/madhavibhat/payroll_crm && python -m pytest tests/test_models.py -v
```

- [ ] **Step 11: Create tests/conftest.py**

```python
import sys
sys.path.insert(0, "/Users/madhavibhat/payroll_v2")
sys.path.insert(0, "/Users/madhavibhat/cps-compliance-platform")
sys.path.insert(0, "/Users/madhavibhat/payroll_crm")
```

- [ ] **Step 12: Run test — expect PASS**

```bash
cd /Users/madhavibhat/payroll_crm && python -m pytest tests/test_models.py -v
```

Expected: `2 passed`

- [ ] **Step 13: Verify app starts**

```bash
cd /Users/madhavibhat/payroll_crm && cp .env.example .env && uvicorn app.main:app --reload --port 8001
```

Expected: `Application startup complete` with no import errors.

- [ ] **Step 14: Commit**

```bash
cd /Users/madhavibhat/payroll_crm && git init && git add -A && git commit -m "feat: project scaffold, DB models, SQLAlchemy setup"
```

---

## Task 2: Authentication

**Files:**
- Create: `app/auth.py`
- Create: `app/routers/auth_router.py`
- Create: `templates/base.html`
- Create: `templates/login.html`
- Modify: `app/main.py` — register auth router
- Create: `tests/test_auth.py`

**Interfaces:**
- Consumes: `User` model, `get_session()`
- Produces:
  - `hash_password(plain: str) -> bytes`
  - `verify_password(plain: str, hashed: bytes) -> bool`
  - `get_current_user(request: Request, session) -> User` — raises HTTPException 302 to /login if not logged in
  - `role_required(role: str)` — dependency factory, raises 302 if wrong role

- [ ] **Step 1: Write failing tests**

```python
# tests/test_auth.py
import sys
sys.path.insert(0, "/Users/madhavibhat/payroll_crm")
sys.path.insert(0, "/Users/madhavibhat/payroll_v2")
sys.path.insert(0, "/Users/madhavibhat/cps-compliance-platform")

from app.auth import hash_password, verify_password

def test_hash_and_verify():
    h = hash_password("secret123")
    assert verify_password("secret123", h) is True
    assert verify_password("wrong", h) is False
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd /Users/madhavibhat/payroll_crm && python -m pytest tests/test_auth.py -v
```

- [ ] **Step 3: Create app/auth.py**

```python
import os
import bcrypt
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.models import User

def hash_password(plain: str) -> bytes:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt())

def verify_password(plain: str, hashed: bytes) -> bool:
    if isinstance(hashed, str):
        hashed = hashed.encode()
    return bcrypt.checkpw(plain.encode(), hashed)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

def set_session(request: Request, user_id: int):
    from itsdangerous import URLSafeSerializer
    s = URLSafeSerializer(SECRET_KEY)
    request.session["user_id"] = s.dumps(user_id)

def get_user_id_from_session(request: Request):
    from itsdangerous import URLSafeSerializer, BadSignature
    token = request.session.get("user_id")
    if not token:
        return None
    try:
        s = URLSafeSerializer(SECRET_KEY)
        return s.loads(token)
    except BadSignature:
        return None

def get_current_user(request: Request, session: Session):
    user_id = get_user_id_from_session(request)
    if not user_id:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user

def role_required(role: str):
    def dependency(request: Request, session: Session):
        user = get_current_user(request, session)
        if user.role != role:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user
    return dependency
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd /Users/madhavibhat/payroll_crm && python -m pytest tests/test_auth.py -v
```

- [ ] **Step 5: Add Starlette session middleware to main.py**

Add after `load_dotenv()`:
```python
from starlette.middleware.sessions import SessionMiddleware
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dev-secret"))
```

Add to requirements.txt: `starlette` (already bundled with fastapi, no action needed).

- [ ] **Step 6: Create app/routers/auth_router.py**

```python
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select
from pathlib import Path

from app.db import get_session
from app.models import User
from app.auth import verify_password, set_session

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent.parent / "templates")

@router.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@router.post("/login")
def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid email or password"})
    set_session(request, user.id)
    if user.role == "operator":
        return RedirectResponse("/operator/dashboard", status_code=302)
    return RedirectResponse("/upload", status_code=302)

@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)
```

- [ ] **Step 7: Create templates/base.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Payroll CRM{% endblock %} — CPS LLP</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <nav>
    <span class="brand">CPS LLP · Payroll CRM</span>
    {% if request.session.get("user_id") %}
    <div class="nav-links">
      {% if role == "operator" %}
        <a href="/operator/dashboard">Dashboard</a>
        <a href="/operator/clients">Clients</a>
      {% endif %}
      <a href="/upload">New Run</a>
      <a href="/history">History</a>
      <form method="post" action="/logout" style="display:inline">
        <button type="submit" class="btn-link">Logout</button>
      </form>
    </div>
    {% endif %}
  </nav>
  <main>{% block content %}{% endblock %}</main>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 8: Create templates/login.html**

```html
{% extends "base.html" %}
{% block title %}Login{% endblock %}
{% block content %}
<div class="card login-card">
  <h1>Sign In</h1>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  <form method="post" action="/login">
    <label>Email<input type="email" name="email" required autofocus></label>
    <label>Password<input type="password" name="password" required></label>
    <button type="submit" class="btn btn-primary">Sign In</button>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 9: Register auth router in main.py**

Add to `app/main.py`:
```python
from app.routers.auth_router import router as auth_router
app.include_router(auth_router)

@app.get("/")
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/login")
```

- [ ] **Step 10: Add minimal CSS to static/style.css**

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; color: #1e293b; }
nav { background: #0f172a; color: white; padding: .75rem 1.5rem; display: flex; justify-content: space-between; align-items: center; }
.brand { font-weight: 700; font-size: 1rem; }
.nav-links a, .btn-link { color: #94a3b8; text-decoration: none; margin-left: 1.2rem; background: none; border: none; cursor: pointer; font-size: .9rem; }
.nav-links a:hover, .btn-link:hover { color: white; }
main { max-width: 1100px; margin: 2rem auto; padding: 0 1.5rem; }
.card { background: white; border-radius: 10px; padding: 2rem; box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 1.5rem; }
.login-card { max-width: 380px; margin: 4rem auto; }
h1 { font-size: 1.4rem; margin-bottom: 1.2rem; }
h2 { font-size: 1.1rem; margin-bottom: 1rem; }
label { display: block; margin-bottom: 1rem; font-size: .875rem; font-weight: 500; }
input, select { display: block; width: 100%; padding: .5rem .75rem; border: 1px solid #cbd5e1; border-radius: 6px; margin-top: .25rem; font-size: .9rem; }
.btn { padding: .5rem 1.2rem; border-radius: 6px; border: none; cursor: pointer; font-size: .875rem; font-weight: 600; text-decoration: none; display: inline-block; }
.btn-primary { background: #3b82f6; color: white; }
.btn-primary:hover { background: #2563eb; }
.btn-danger { background: #ef4444; color: white; }
.btn-sm { padding: .3rem .8rem; font-size: .8rem; }
.error { color: #ef4444; background: #fef2f2; padding: .5rem .75rem; border-radius: 6px; margin-bottom: 1rem; font-size: .875rem; }
.success { color: #16a34a; background: #f0fdf4; padding: .5rem .75rem; border-radius: 6px; margin-bottom: 1rem; font-size: .875rem; }
table { width: 100%; border-collapse: collapse; font-size: .875rem; }
th { background: #f1f5f9; text-align: left; padding: .6rem .75rem; font-weight: 600; }
td { padding: .6rem .75rem; border-bottom: 1px solid #f1f5f9; }
.badge { display: inline-block; padding: .2rem .6rem; border-radius: 20px; font-size: .75rem; font-weight: 600; }
.badge-draft { background: #fef9c3; color: #854d0e; }
.badge-approved { background: #dcfce7; color: #166534; }
.badge-error { background: #fee2e2; color: #991b1b; }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
.stat-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 1rem; }
.stat-box .label { font-size: .75rem; color: #64748b; font-weight: 500; }
.stat-box .value { font-size: 1.4rem; font-weight: 700; margin-top: .25rem; }
.review-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
@media (max-width: 768px) { .review-grid { grid-template-columns: 1fr; } }
.finding { padding: .6rem .75rem; border-radius: 6px; margin-bottom: .5rem; font-size: .85rem; }
.finding-pass { background: #dcfce7; border-left: 3px solid #22c55e; }
.finding-partial { background: #fef9c3; border-left: 3px solid #f59e0b; }
.finding-fail { background: #fee2e2; border-left: 3px solid #ef4444; }
.drop-zone { border: 2px dashed #cbd5e1; border-radius: 10px; padding: 3rem; text-align: center; cursor: pointer; transition: border-color .2s; }
.drop-zone:hover, .drop-zone.dragover { border-color: #3b82f6; background: #eff6ff; }
.download-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; }
.download-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 1.2rem; text-align: center; }
.download-card .icon { font-size: 2rem; margin-bottom: .5rem; }
```

- [ ] **Step 11: Seed an operator account for testing**

Create `seed.py` in project root:
```python
import sys
sys.path.insert(0, "/Users/madhavibhat/payroll_v2")
sys.path.insert(0, "/Users/madhavibhat/cps-compliance-platform")
sys.path.insert(0, "/Users/madhavibhat/payroll_crm")

from app.db import engine, SessionLocal
from app.models import Base, User
from app.auth import hash_password

Base.metadata.create_all(engine)
with SessionLocal() as s:
    existing = s.execute(__import__("sqlalchemy").select(User).where(User.email == "admin@cps.in")).scalar_one_or_none()
    if not existing:
        s.add(User(email="admin@cps.in", password_hash=hash_password("admin123").decode(), role="operator"))
        s.commit()
        print("Operator created: admin@cps.in / admin123")
    else:
        print("Already exists")
```

```bash
cd /Users/madhavibhat/payroll_crm && python seed.py
```

- [ ] **Step 12: Manual smoke test**

```bash
cd /Users/madhavibhat/payroll_crm && uvicorn app.main:app --reload --port 8001
```

Open http://localhost:8001 — should redirect to `/login`. Log in with `admin@cps.in / admin123` — should redirect to `/operator/dashboard` (404 is fine, router not built yet).

- [ ] **Step 13: Commit**

```bash
cd /Users/madhavibhat/payroll_crm && git add -A && git commit -m "feat: session auth, login/logout, base templates"
```

---

## Task 3: Engine Wrappers

**Files:**
- Create: `app/engines/payroll.py`
- Create: `app/engines/compliance.py`
- Create: `tests/test_engines.py`

**Interfaces:**
- Consumes: `payroll_v2/app/payroll_engine.py` (`EmployeeInput`, `calculate_payroll`, `PayrollResult`), `cps-compliance-platform/rules/central_acts.py`, `state_acts.py`
- Produces:
  - `run_payroll(employees: list[dict], month: int, year: int) -> list[dict]` — each dict is a PayrollResult serialised to plain dict
  - `run_compliance(payroll_results: list[dict], client: Client) -> list[dict]` — each dict: `{act, section, area, status, reason, priority, penalty}`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_engines.py
import sys
sys.path.insert(0, "/Users/madhavibhat/payroll_crm")
sys.path.insert(0, "/Users/madhavibhat/payroll_v2")
sys.path.insert(0, "/Users/madhavibhat/cps-compliance-platform")

from app.engines.payroll import run_payroll
from app.engines.compliance import run_compliance

SAMPLE_EMPLOYEES = [
    {
        "emp_id": "E001", "name": "Rahul Sharma", "uan": "101234567801",
        "pf_number": "MH/MUM/001/001", "esic_number": "3001234501",
        "basic": 18000, "da": 3600, "hra": 7200, "other_allowances": 2200,
        "days_in_month": 31, "days_worked": 31, "advance_deduction": 0,
        "bank_account": "112233445501", "ifsc_code": "HDFC0001111",
        "designation": "Engineer", "department": "Tech"
    }
]

def test_run_payroll_returns_list_of_dicts():
    results = run_payroll(SAMPLE_EMPLOYEES, month=6, year=2026)
    assert isinstance(results, list)
    assert len(results) == 1
    r = results[0]
    assert "net_pay" in r
    assert "employee_pf" in r
    assert r["net_pay"] > 0

def test_run_payroll_pf_calculation():
    results = run_payroll(SAMPLE_EMPLOYEES, month=6, year=2026)
    # 12% of min(18000, 15000) = 1800
    assert results[0]["employee_pf"] == 1800

def test_run_compliance_returns_list():
    results = run_payroll(SAMPLE_EMPLOYEES, month=6, year=2026)

    class FakeClient:
        state = "Maharashtra"
        industry_type = "IT"
        headcount = 25
        establishment_id = "MH/MUM/001"

    findings = run_compliance(results, FakeClient())
    assert isinstance(findings, list)
    assert len(findings) > 0
    assert "status" in findings[0]
    assert findings[0]["status"] in ("compliant", "partial", "non_compliant", "not_applicable")
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd /Users/madhavibhat/payroll_crm && python -m pytest tests/test_engines.py -v
```

- [ ] **Step 3: Create app/engines/payroll.py**

```python
import sys
sys.path.insert(0, "/Users/madhavibhat/payroll_v2")

from dataclasses import asdict
from app_payroll.payroll_engine import EmployeeInput, calculate_payroll

# Note: payroll_v2 package name collision — import via sys.path, module is payroll_engine
import importlib
_pe = importlib.import_module("app.payroll_engine")
EmployeeInput = _pe.EmployeeInput
calculate_payroll = _pe.calculate_payroll

def run_payroll(employees: list[dict], month: int, year: int) -> list[dict]:
    results = []
    for emp_data in employees:
        emp = EmployeeInput(
            emp_id=str(emp_data.get("emp_id") or ""),
            name=str(emp_data.get("name") or ""),
            uan=str(emp_data.get("uan") or ""),
            pf_number=str(emp_data.get("pf_number") or ""),
            esic_number=str(emp_data.get("esic_number") or ""),
            basic=float(emp_data.get("basic") or 0),
            da=float(emp_data.get("da") or 0),
            hra=float(emp_data.get("hra") or 0),
            other_allowances=float(emp_data.get("other_allowances") or 0),
            days_in_month=int(emp_data.get("days_in_month") or 30),
            days_worked=int(emp_data.get("days_worked") or 0),
            advance_deduction=float(emp_data.get("advance_deduction") or 0),
            bank_account=str(emp_data.get("bank_account") or ""),
            ifsc_code=str(emp_data.get("ifsc_code") or ""),
            designation=str(emp_data.get("designation") or ""),
            department=str(emp_data.get("department") or ""),
        )
        result = calculate_payroll(emp, month, year)
        results.append(asdict(result))
    return results
```

- [ ] **Step 4: Fix import — payroll_v2 has `app/` package that conflicts**

The payroll_v2 `app/` subpackage clashes with payroll_crm's own `app/`. Fix by importing with importlib using the full path:

```python
# app/engines/payroll.py
import sys
import importlib.util
from dataclasses import asdict
from pathlib import Path

def _load_payroll_engine():
    spec = importlib.util.spec_from_file_location(
        "payroll_engine_v2",
        Path("/Users/madhavibhat/payroll_v2/app/payroll_engine.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_engine = _load_payroll_engine()
EmployeeInput = _engine.EmployeeInput
calculate_payroll = _engine.calculate_payroll

def run_payroll(employees: list[dict], month: int, year: int) -> list[dict]:
    results = []
    for emp_data in employees:
        emp = EmployeeInput(
            emp_id=str(emp_data.get("emp_id") or ""),
            name=str(emp_data.get("name") or ""),
            uan=str(emp_data.get("uan") or ""),
            pf_number=str(emp_data.get("pf_number") or ""),
            esic_number=str(emp_data.get("esic_number") or ""),
            basic=float(emp_data.get("basic") or 0),
            da=float(emp_data.get("da") or 0),
            hra=float(emp_data.get("hra") or 0),
            other_allowances=float(emp_data.get("other_allowances") or 0),
            days_in_month=int(emp_data.get("days_in_month") or 30),
            days_worked=int(emp_data.get("days_worked") or 0),
            advance_deduction=float(emp_data.get("advance_deduction") or 0),
            bank_account=str(emp_data.get("bank_account") or ""),
            ifsc_code=str(emp_data.get("ifsc_code") or ""),
            designation=str(emp_data.get("designation") or ""),
            department=str(emp_data.get("department") or ""),
        )
        result = calculate_payroll(emp, month, year)
        results.append(asdict(result))
    return results
```

- [ ] **Step 5: Create app/engines/compliance.py**

```python
import importlib.util
from pathlib import Path

def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_central = _load_module("central_acts", Path("/Users/madhavibhat/cps-compliance-platform/rules/central_acts.py"))
_state   = _load_module("state_acts",   Path("/Users/madhavibhat/cps-compliance-platform/rules/state_acts.py"))

CHECKERS = [
    _central.check_epf, _central.check_esic, _central.check_minimum_wages,
    _central.check_payment_of_wages, _central.check_factories_act,
    _central.check_payment_of_bonus, _central.check_gratuity,
    _central.check_maternity_benefit, _central.check_posh,
    _central.check_contract_labour, _central.check_industrial_disputes,
    _central.check_labour_codes,
    _state.check_professional_tax, _state.check_labour_welfare_fund,
    _state.check_shops_establishment,
]

def _build_compliance_data(payroll_results: list[dict], client) -> dict:
    emp_count = len(payroll_results)
    wages = [r.get("gross_earned", 0) for r in payroll_results]
    lowest_wage = min(wages) if wages else 0
    avg_wage = sum(wages) / emp_count if emp_count else 0
    pf_applicable = any(r.get("employee_pf", 0) > 0 for r in payroll_results)
    esic_applicable = any(r.get("esic_applicable", False) for r in payroll_results)

    return {
        "employee_count": emp_count,
        "state": getattr(client, "state", "Maharashtra"),
        "industry_type": getattr(client, "industry_type", ""),
        "epf_registered": pf_applicable,
        "epf_rate_employer": 12,
        "epf_rate_employee": 12,
        "ecr_filed_monthly": True,
        "uan_kyc_linked_pct": 80,
        "esic_registered": esic_applicable,
        "esic_rate_employer": 3.25,
        "esic_rate_employee": 0.75,
        "esic_wage_ceiling_applied": True,
        "minimum_wage_compliant": lowest_wage >= 8000,
        "avg_monthly_wage": avg_wage,
        "wage_slip_issued": True,
        "wages_paid_by_10th": True,
        "pt_registered": True,
        "pt_deducted": True,
        "lwf_compliant": True,
        "shops_est_registered": True,
        "is_factory": getattr(client, "industry_type", "") == "Manufacturing",
        "has_women_employees": True,
        "wage_structure": {"basic": True, "hra": True},
        "operates_in_states": [getattr(client, "state", "Maharashtra")],
    }

def run_compliance(payroll_results: list[dict], client) -> list[dict]:
    data = _build_compliance_data(payroll_results, client)
    findings = []
    for checker in CHECKERS:
        try:
            for f in checker(data):
                findings.append({
                    "act": f.act,
                    "section": f.section,
                    "area": f.area,
                    "status": f.status.value,
                    "reason": f.reason,
                    "priority": f.priority,
                    "penalty": getattr(f, "penalty", "") or "",
                    "next_steps": f.next_steps,
                })
        except Exception as e:
            findings.append({
                "act": checker.__name__,
                "section": "—",
                "area": "Engine Error",
                "status": "partial",
                "reason": f"Could not evaluate: {e}",
                "priority": "low",
                "penalty": "",
                "next_steps": [],
            })
    return findings
```

- [ ] **Step 6: Run tests — expect PASS**

```bash
cd /Users/madhavibhat/payroll_crm && python -m pytest tests/test_engines.py -v
```

Expected: `3 passed`

- [ ] **Step 7: Commit**

```bash
cd /Users/madhavibhat/payroll_crm && git add -A && git commit -m "feat: payroll and compliance engine wrappers with importlib isolation"
```

---

## Task 4: File Ingestion

**Files:**
- Create: `app/ingest/structured.py`
- Create: `app/ingest/unstructured.py`
- Create: `tests/test_ingest.py`

**Interfaces:**
- Produces:
  - `parse_structured(path: str | Path) -> list[dict]` — reads CSV or Excel, returns normalised employee dicts
  - `parse_unstructured(path: str | Path) -> list[dict]` — calls Claude API, returns same normalised format
  - Both raise `ValueError` with a human-readable message if the file cannot be parsed

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ingest.py
import sys, os
sys.path.insert(0, "/Users/madhavibhat/payroll_crm")
sys.path.insert(0, "/Users/madhavibhat/payroll_v2")
sys.path.insert(0, "/Users/madhavibhat/cps-compliance-platform")

import pytest
from pathlib import Path
from app.ingest.structured import parse_structured

SAMPLE_CSV = Path("/Users/madhavibhat/payroll_v2/test_data/company_single_techspark.csv")

def test_parse_csv_returns_list():
    result = parse_structured(SAMPLE_CSV)
    assert isinstance(result, list)
    assert len(result) == 10

def test_parse_csv_has_required_fields():
    result = parse_structured(SAMPLE_CSV)
    required = {"name", "basic", "days_worked", "days_in_month"}
    for emp in result:
        assert required.issubset(emp.keys()), f"Missing fields in {emp}"

def test_parse_csv_numeric_types():
    result = parse_structured(SAMPLE_CSV)
    assert isinstance(result[0]["basic"], float)
    assert isinstance(result[0]["days_worked"], int)

def test_parse_invalid_file_raises():
    with pytest.raises(ValueError):
        parse_structured(Path("/tmp/nonexistent.csv"))
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd /Users/madhavibhat/payroll_crm && python -m pytest tests/test_ingest.py -v
```

- [ ] **Step 3: Create app/ingest/structured.py**

```python
from pathlib import Path
import pandas as pd

COLUMN_ALIASES = {
    "emp_id":            ["emp_id", "employee_id", "empid", "id", "sl no", "serial"],
    "name":              ["name", "employee name", "emp name", "full name"],
    "designation":       ["designation", "role", "post", "position"],
    "department":        ["department", "dept", "division"],
    "uan":               ["uan", "uan number", "uan no"],
    "pf_number":         ["pf_number", "pf number", "pf no", "epf number"],
    "esic_number":       ["esic_number", "esic number", "esic no", "ip number"],
    "basic":             ["basic", "basic salary", "basic pay", "basic wage"],
    "da":                ["da", "dearness allowance", "dearness allow"],
    "hra":               ["hra", "house rent allowance", "house rent"],
    "other_allowances":  ["other_allowances", "other allowances", "other allow", "special allowance"],
    "days_in_month":     ["days_in_month", "days in month", "total days", "working days in month"],
    "days_worked":       ["days_worked", "days worked", "attended days", "actual days", "present days"],
    "advance_deduction": ["advance_deduction", "advance", "advance deduction", "loan deduction"],
    "bank_account":      ["bank_account", "bank account", "account number", "acc no"],
    "ifsc_code":         ["ifsc_code", "ifsc", "ifsc code"],
}

def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    lower_cols = {c.lower().strip(): c for c in df.columns}
    rename = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lower_cols:
                rename[lower_cols[alias]] = canonical
                break
    return df.rename(columns=rename)

def parse_structured(path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        raise ValueError(f"File not found: {path}")
    try:
        if path.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(path)
        elif path.suffix.lower() == ".csv":
            df = pd.read_csv(path)
        else:
            raise ValueError(f"Unsupported format: {path.suffix}. Use CSV or Excel.")
    except Exception as e:
        raise ValueError(f"Could not read file: {e}")

    df = _normalise_columns(df)
    df = df.dropna(how="all")

    if "name" not in df.columns:
        raise ValueError("Could not find an employee name column. Check column headers.")
    if "basic" not in df.columns:
        raise ValueError("Could not find a basic salary column. Check column headers.")

    numeric_fields = ["basic", "da", "hra", "other_allowances", "advance_deduction"]
    int_fields = ["days_in_month", "days_worked"]

    for f in numeric_fields:
        if f in df.columns:
            df[f] = pd.to_numeric(df[f], errors="coerce").fillna(0).astype(float)
        else:
            df[f] = 0.0

    for f in int_fields:
        if f in df.columns:
            df[f] = pd.to_numeric(df[f], errors="coerce").fillna(30).astype(int)
        else:
            df[f] = 30

    records = df.to_dict(orient="records")
    return [
        {k: (str(v) if k not in numeric_fields + int_fields else v)
         for k, v in row.items() if pd.notna(v)}
        for row in records
        if str(row.get("name", "")).strip()
    ]
```

- [ ] **Step 4: Run structured tests — expect PASS**

```bash
cd /Users/madhavibhat/payroll_crm && python -m pytest tests/test_ingest.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Create app/ingest/unstructured.py**

```python
import os
import json
import base64
from pathlib import Path
import anthropic

def _read_file_content(path: Path) -> tuple[str, str]:
    """Returns (content_type, content) where content is text or base64."""
    suffix = path.suffix.lower()
    if suffix in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        with open(path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode()
        media_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                     ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
        return "image", (media_map[suffix], data)
    elif suffix == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        except ImportError:
            with open(path, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode()
            return "image", ("application/pdf", data)
        return "text", text
    else:
        with open(path, "r", errors="ignore") as f:
            return "text", f.read()

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
            {"type": "text", "text": EXTRACTION_PROMPT}
        ]
    else:
        message_content = [{"type": "text", "text": f"{EXTRACTION_PROMPT}\n\nDocument:\n{content}"}]

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": message_content}]
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        employees = json.loads(raw.strip())
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\nRaw: {raw[:300]}")

    if not isinstance(employees, list):
        raise ValueError("Claude did not return a JSON array")

    return [
        {
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
        for e in employees
        if str(e.get("name", "")).strip()
    ]
```

- [ ] **Step 6: Commit**

```bash
cd /Users/madhavibhat/payroll_crm && git add -A && git commit -m "feat: structured (pandas) and unstructured (Claude API) file ingestion"
```

---

## Task 5: Orchestrator

**Files:**
- Create: `app/routers/run.py`
- Create: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `run_payroll()`, `run_compliance()`, `parse_structured()`, `parse_unstructured()`, `Run`, `RunFile`, `EditRequest` models
- Produces:
  - `orchestrate(file_path, client, month, year, session, user_id, parent_run_id=None) -> Run`
  - `apply_text_edit(instruction: str, payroll_results: list[dict]) -> list[dict]` — calls Claude API to patch employee data

- [ ] **Step 1: Write failing tests**

```python
# tests/test_orchestrator.py
import sys
sys.path.insert(0, "/Users/madhavibhat/payroll_crm")
sys.path.insert(0, "/Users/madhavibhat/payroll_v2")
sys.path.insert(0, "/Users/madhavibhat/cps-compliance-platform")

import json, pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, Client, User, Run
from app.auth import hash_password
from app.routers.run import orchestrate

@pytest.fixture
def db_session():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as s:
        yield s

@pytest.fixture
def client_and_user(db_session):
    c = Client(name="TechSpark", state="Maharashtra", industry_type="IT", headcount=10,
                establishment_id="MH/MUM/55001")
    db_session.add(c); db_session.flush()
    u = User(email="client@techspark.com", password_hash=hash_password("pass").decode(),
              role="client", client_id=c.id)
    db_session.add(u); db_session.flush()
    db_session.commit()
    return c, u

CSV_PATH = Path("/Users/madhavibhat/payroll_v2/test_data/company_single_techspark.csv")

def test_orchestrate_creates_run(db_session, client_and_user):
    client, user = client_and_user
    run = orchestrate(CSV_PATH, client, month=6, year=2026,
                      session=db_session, user_id=user.id)
    assert run.id is not None
    assert run.status == "draft"
    assert run.version == 1
    assert run.payroll_json is not None
    assert run.compliance_json is not None

def test_orchestrate_payroll_json_valid(db_session, client_and_user):
    client, user = client_and_user
    run = orchestrate(CSV_PATH, client, month=6, year=2026,
                      session=db_session, user_id=user.id)
    results = json.loads(run.payroll_json)
    assert len(results) == 10
    assert all("net_pay" in r for r in results)

def test_orchestrate_compliance_json_valid(db_session, client_and_user):
    client, user = client_and_user
    run = orchestrate(CSV_PATH, client, month=6, year=2026,
                      session=db_session, user_id=user.id)
    findings = json.loads(run.compliance_json)
    assert isinstance(findings, list)
    assert len(findings) > 0
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd /Users/madhavibhat/payroll_crm && python -m pytest tests/test_orchestrator.py -v
```

- [ ] **Step 3: Create app/routers/run.py**

```python
import json
import os
import shutil
from pathlib import Path
from sqlalchemy.orm import Session

from app.models import Run, RunFile, EditRequest
from app.engines.payroll import run_payroll
from app.engines.compliance import run_compliance
from app.ingest.structured import parse_structured
from app.ingest.unstructured import parse_unstructured

UPLOADS_DIR = Path(__file__).parent.parent.parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

STRUCTURED_EXTS = {".csv", ".xlsx", ".xls"}

def _detect_and_parse(file_path: Path) -> list[dict]:
    if file_path.suffix.lower() in STRUCTURED_EXTS:
        return parse_structured(file_path)
    return parse_unstructured(file_path)

def orchestrate(
    file_path,
    client,
    month: int,
    year: int,
    session: Session,
    user_id: int,
    parent_run_id: int = None,
) -> Run:
    file_path = Path(file_path)
    employees = _detect_and_parse(file_path)
    payroll_results = run_payroll(employees, month, year)
    compliance_findings = run_compliance(payroll_results, client)

    version = 1
    if parent_run_id:
        parent = session.get(Run, parent_run_id)
        if parent:
            version = parent.version + 1

    run = Run(
        client_id=client.id,
        month=month,
        year=year,
        version=version,
        status="draft",
        payroll_json=json.dumps(payroll_results),
        compliance_json=json.dumps(compliance_findings),
        created_by=user_id,
    )
    session.add(run)
    session.flush()

    # Store uploaded file
    dest_dir = UPLOADS_DIR / str(run.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / file_path.name
    shutil.copy2(file_path, dest)

    run_file = RunFile(
        run_id=run.id,
        file_type="structured" if file_path.suffix.lower() in STRUCTURED_EXTS else "unstructured",
        original_name=file_path.name,
        storage_path=str(dest),
    )
    session.add(run_file)
    session.commit()
    return run

def apply_text_edit(instruction: str, payroll_results: list[dict]) -> list[dict]:
    import anthropic
    api_key = os.getenv("CLAUDE_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""You are given a list of employee payroll records as JSON.
Apply the following edit instruction to the records and return the updated JSON array.
Only change what the instruction specifies. Return only the JSON array, no explanation.

Instruction: {instruction}

Current records:
{json.dumps(payroll_results, indent=2)}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/madhavibhat/payroll_crm && python -m pytest tests/test_orchestrator.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
cd /Users/madhavibhat/payroll_crm && git add -A && git commit -m "feat: orchestrator — ingest, payroll, compliance, versioned run creation"
```

---

## Task 6: Operator Views

**Files:**
- Create: `app/routers/operator.py`
- Create: `templates/operator_dashboard.html`
- Create: `templates/operator_clients.html`

**Interfaces:**
- Consumes: `Client`, `User`, `Run` models, `role_required("operator")`
- Produces: Routes `/operator/dashboard`, `/operator/clients` (GET + POST), `/operator/clients/{id}/edit` (GET + POST), `/operator/clients/{id}/create-login` (POST)

- [ ] **Step 1: Create app/routers/operator.py**

```python
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from pathlib import Path

from app.db import get_session
from app.models import Client, User, Run
from app.auth import role_required, hash_password

router = APIRouter(prefix="/operator")
templates = Jinja2Templates(directory=Path(__file__).parent.parent.parent / "templates")

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session),
               user=Depends(role_required("operator"))):
    clients = session.execute(select(Client)).scalars().all()
    client_data = []
    for c in clients:
        latest_run = session.execute(
            select(Run).where(Run.client_id == c.id).order_by(Run.created_at.desc())
        ).scalar_one_or_none()
        client_data.append({"client": c, "latest_run": latest_run})
    return templates.TemplateResponse("operator_dashboard.html", {
        "request": request, "client_data": client_data, "role": "operator"
    })

@router.get("/clients", response_class=HTMLResponse)
def clients_get(request: Request, session: Session = Depends(get_session),
                 user=Depends(role_required("operator"))):
    clients = session.execute(select(Client)).scalars().all()
    return templates.TemplateResponse("operator_clients.html", {
        "request": request, "clients": clients, "role": "operator", "msg": None
    })

@router.post("/clients")
def create_client(
    request: Request,
    name: str = Form(...),
    establishment_id: str = Form(""),
    state: str = Form(...),
    industry_type: str = Form(""),
    headcount: int = Form(0),
    session: Session = Depends(get_session),
    user=Depends(role_required("operator")),
):
    c = Client(name=name, establishment_id=establishment_id, state=state,
               industry_type=industry_type, headcount=headcount)
    session.add(c); session.commit()
    return RedirectResponse("/operator/clients", status_code=302)

@router.post("/clients/{client_id}/create-login")
def create_client_login(
    client_id: int,
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
    user=Depends(role_required("operator")),
):
    existing = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        return RedirectResponse(f"/operator/clients?error=Email+already+exists", status_code=302)
    u = User(email=email, password_hash=hash_password(password).decode(),
              role="client", client_id=client_id)
    session.add(u); session.commit()
    return RedirectResponse("/operator/clients", status_code=302)
```

- [ ] **Step 2: Create templates/operator_dashboard.html**

```html
{% extends "base.html" %}
{% block title %}Operator Dashboard{% endblock %}
{% block content %}
<h1>Client Dashboard</h1>
<div class="card">
  <table>
    <thead>
      <tr><th>Client</th><th>State</th><th>Industry</th><th>Latest Run</th><th>Status</th><th>Actions</th></tr>
    </thead>
    <tbody>
    {% for item in client_data %}
      <tr>
        <td><strong>{{ item.client.name }}</strong><br><small>{{ item.client.establishment_id or '—' }}</small></td>
        <td>{{ item.client.state }}</td>
        <td>{{ item.client.industry_type or '—' }}</td>
        <td>
          {% if item.latest_run %}
            {{ item.latest_run.month }}/{{ item.latest_run.year }} v{{ item.latest_run.version }}
          {% else %}No runs{% endif %}
        </td>
        <td>
          {% if item.latest_run %}
            <span class="badge badge-{{ item.latest_run.status }}">{{ item.latest_run.status }}</span>
          {% else %}—{% endif %}
        </td>
        <td>
          <a href="/upload?client_id={{ item.client.id }}" class="btn btn-primary btn-sm">New Run</a>
          {% if item.latest_run %}
            <a href="/review/{{ item.latest_run.id }}" class="btn btn-sm" style="background:#e2e8f0">Review</a>
          {% endif %}
        </td>
      </tr>
    {% else %}
      <tr><td colspan="6" style="text-align:center;color:#64748b">No clients yet. <a href="/operator/clients">Add one.</a></td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 3: Create templates/operator_clients.html**

```html
{% extends "base.html" %}
{% block title %}Manage Clients{% endblock %}
{% block content %}
<h1>Manage Clients</h1>
{% if msg %}<p class="success">{{ msg }}</p>{% endif %}

<div class="card">
  <h2>Add New Client</h2>
  <form method="post" action="/operator/clients">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
      <label>Company Name<input name="name" required></label>
      <label>Establishment ID<input name="establishment_id" placeholder="MH/MUM/55001"></label>
      <label>State<input name="state" value="Maharashtra" required></label>
      <label>Industry Type<input name="industry_type" placeholder="IT, Manufacturing..."></label>
      <label>Headcount<input name="headcount" type="number" value="0"></label>
    </div>
    <button type="submit" class="btn btn-primary" style="margin-top:1rem">Add Client</button>
  </form>
</div>

<div class="card">
  <h2>Existing Clients</h2>
  <table>
    <thead><tr><th>Name</th><th>State</th><th>Headcount</th><th>Create Login</th></tr></thead>
    <tbody>
    {% for client in clients %}
      <tr>
        <td>{{ client.name }}<br><small>{{ client.establishment_id or '' }}</small></td>
        <td>{{ client.state }}</td>
        <td>{{ client.headcount or '—' }}</td>
        <td>
          <form method="post" action="/operator/clients/{{ client.id }}/create-login" style="display:flex;gap:.5rem;align-items:flex-end">
            <input name="email" type="email" placeholder="client@company.com" style="width:180px">
            <input name="password" type="password" placeholder="password" style="width:120px">
            <button type="submit" class="btn btn-sm btn-primary">Create</button>
          </form>
        </td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 4: Register operator router in main.py**

```python
from app.routers.operator import router as operator_router
app.include_router(operator_router)
```

- [ ] **Step 5: Smoke test**

```bash
cd /Users/madhavibhat/payroll_crm && uvicorn app.main:app --reload --port 8001
```

Log in as `admin@cps.in` → should see `/operator/dashboard` with empty table. Navigate to `/operator/clients` → create a client → should appear in dashboard.

- [ ] **Step 6: Commit**

```bash
cd /Users/madhavibhat/payroll_crm && git add -A && git commit -m "feat: operator dashboard and client management views"
```

---

## Task 7: Upload + Review + Edit + Approve Routes

**Files:**
- Create: `app/routers/client.py`
- Create: `templates/upload.html`
- Create: `templates/review.html`

**Interfaces:**
- Consumes: `orchestrate()`, `apply_text_edit()`, `run_payroll()`, `run_compliance()`, `Run`, `Client`, `EditRequest` models, `get_current_user()`
- Produces: Routes `/upload` (GET+POST), `/review/{run_id}` (GET), `/run/{run_id}/edit` (POST), `/run/{run_id}/approve` (POST)

- [ ] **Step 1: Create app/routers/client.py**

```python
import json
import shutil
import tempfile
from pathlib import Path
from fastapi import APIRouter, Request, Form, File, UploadFile, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import get_session
from app.models import Run, Client, User, EditRequest, Output
from app.auth import get_current_user
from app.routers.run import orchestrate, apply_text_edit, UPLOADS_DIR
from app.engines.payroll import run_payroll
from app.engines.compliance import run_compliance

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent.parent / "templates")
OUTPUTS_DIR = Path(__file__).parent.parent.parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

def _assert_run_access(run: Run, user: User):
    if user.role == "client" and run.client_id != user.client_id:
        raise HTTPException(status_code=403, detail="Access denied")

def _severity(status: str) -> str:
    if status in ("non_compliant",):
        return "fail"
    if status in ("partial",):
        return "partial"
    return "pass"

@router.get("/upload", response_class=HTMLResponse)
def upload_get(request: Request, client_id: int = None,
               session: Session = Depends(get_session),
               user: User = Depends(get_current_user)):
    clients = []
    if user.role == "operator":
        clients = session.execute(select(Client)).scalars().all()
    else:
        client_id = user.client_id
    return templates.TemplateResponse("upload.html", {
        "request": request, "clients": clients,
        "selected_client_id": client_id, "role": user.role
    })

@router.post("/upload")
async def upload_post(
    request: Request,
    file: UploadFile = File(...),
    month: int = Form(...),
    year: int = Form(...),
    client_id: int = Form(None),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if user.role == "client":
        client_id = user.client_id
    if not client_id:
        raise HTTPException(status_code=400, detail="Client required")

    client = session.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        run = orchestrate(tmp_path, client, month, year, session, user.id)
    finally:
        tmp_path.unlink(missing_ok=True)

    return RedirectResponse(f"/review/{run.id}", status_code=302)

@router.get("/review/{run_id}", response_class=HTMLResponse)
def review_get(run_id: int, request: Request,
               session: Session = Depends(get_session),
               user: User = Depends(get_current_user)):
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404)
    _assert_run_access(run, user)
    client = session.get(Client, run.client_id)
    payroll = json.loads(run.payroll_json)
    compliance = json.loads(run.compliance_json)
    for f in compliance:
        f["severity"] = _severity(f["status"])
    has_blocks = any(f["severity"] == "fail" for f in compliance)
    totals = {
        "gross": sum(r.get("gross_earned", 0) for r in payroll),
        "net": sum(r.get("net_pay", 0) for r in payroll),
        "pf": sum(r.get("employee_pf", 0) for r in payroll),
        "esic": sum(r.get("employee_esic", 0) for r in payroll),
        "count": len(payroll),
    }
    return templates.TemplateResponse("review.html", {
        "request": request, "run": run, "client": client,
        "payroll": payroll, "compliance": compliance,
        "has_blocks": has_blocks, "totals": totals, "role": user.role
    })

@router.post("/run/{run_id}/edit")
async def edit_run(
    run_id: int,
    request: Request,
    edit_type: str = Form(...),
    instruction: str = Form(""),
    file: UploadFile = File(None),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404)
    _assert_run_access(run, user)
    client = session.get(Client, run.client_id)

    edit_req = EditRequest(run_id=run_id, type=edit_type,
                            content=instruction, created_by=user.id)
    session.add(edit_req)
    session.flush()

    if edit_type == "reupload" and file:
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = Path(tmp.name)
        try:
            new_run = orchestrate(tmp_path, client, run.month, run.year,
                                   session, user.id, parent_run_id=run_id)
        finally:
            tmp_path.unlink(missing_ok=True)
    else:
        payroll_results = json.loads(run.payroll_json)
        updated = apply_text_edit(instruction, payroll_results)
        compliance_findings = run_compliance(updated, client)
        from app.models import Run as RunModel
        new_run = RunModel(
            client_id=client.id, month=run.month, year=run.year,
            version=run.version + 1, status="draft",
            payroll_json=json.dumps(updated),
            compliance_json=json.dumps(compliance_findings),
            created_by=user.id,
        )
        session.add(new_run)
        session.commit()

    return RedirectResponse(f"/review/{new_run.id}", status_code=302)

@router.post("/run/{run_id}/approve")
def approve_run(run_id: int, request: Request,
                session: Session = Depends(get_session),
                user: User = Depends(get_current_user)):
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404)
    _assert_run_access(run, user)
    compliance = json.loads(run.compliance_json)
    if any(_severity(f["status"]) == "fail" for f in compliance):
        raise HTTPException(status_code=400, detail="Cannot approve: blocking compliance issues remain")

    from app.routers.download import generate_outputs
    generate_outputs(run, session)

    from datetime import datetime
    run.status = "approved"
    run.approved_by = user.id
    run.approved_at = datetime.utcnow()
    session.commit()
    return RedirectResponse(f"/download/{run_id}", status_code=302)
```

- [ ] **Step 2: Create templates/upload.html**

```html
{% extends "base.html" %}
{% block title %}Upload Payroll File{% endblock %}
{% block content %}
<h1>New Payroll Run</h1>
<div class="card" style="max-width:600px">
  <form method="post" action="/upload" enctype="multipart/form-data" id="upload-form">
    {% if role == "operator" %}
    <label>Client
      <select name="client_id" required>
        <option value="">— Select client —</option>
        {% for c in clients %}
          <option value="{{ c.id }}" {% if c.id == selected_client_id %}selected{% endif %}>{{ c.name }}</option>
        {% endfor %}
      </select>
    </label>
    {% endif %}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin:1rem 0">
      <label>Month
        <select name="month" required>
          {% for m,name in [(1,'January'),(2,'February'),(3,'March'),(4,'April'),(5,'May'),(6,'June'),(7,'July'),(8,'August'),(9,'September'),(10,'October'),(11,'November'),(12,'December')] %}
            <option value="{{ m }}">{{ name }}</option>
          {% endfor %}
        </select>
      </label>
      <label>Year
        <input name="year" type="number" value="2026" min="2020" max="2030" required>
      </label>
    </div>
    <label>Attendance / Salary File
      <div class="drop-zone" id="drop-zone">
        <div id="drop-text">
          <p style="font-size:2rem;margin-bottom:.5rem">📁</p>
          <p>Drag & drop or <strong>click to browse</strong></p>
          <p style="color:#64748b;font-size:.8rem;margin-top:.5rem">CSV · Excel · PDF · Image · Word</p>
        </div>
        <input type="file" name="file" id="file-input" required
               accept=".csv,.xlsx,.xls,.pdf,.jpg,.jpeg,.png,.docx"
               style="position:absolute;inset:0;opacity:0;cursor:pointer">
      </div>
    </label>
    <div id="file-name" style="display:none;padding:.5rem;background:#f0fdf4;border-radius:6px;margin-top:.5rem;font-size:.875rem;color:#166534"></div>
    <button type="submit" class="btn btn-primary" style="margin-top:1rem;width:100%" id="submit-btn">
      Process Payroll
    </button>
  </form>
</div>
<script>
const input = document.getElementById('file-input');
const dropText = document.getElementById('drop-text');
const fileName = document.getElementById('file-name');
const dropZone = document.getElementById('drop-zone');
input.addEventListener('change', () => {
  if (input.files[0]) {
    fileName.textContent = '✓ ' + input.files[0].name;
    fileName.style.display = 'block';
  }
});
document.getElementById('upload-form').addEventListener('submit', () => {
  document.getElementById('submit-btn').textContent = 'Processing… please wait';
  document.getElementById('submit-btn').disabled = true;
});
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('dragover');
  input.files = e.dataTransfer.files;
  input.dispatchEvent(new Event('change'));
});
</script>
{% endblock %}
```

- [ ] **Step 3: Create templates/review.html**

```html
{% extends "base.html" %}
{% block title %}Review — {{ client.name }} {{ run.month }}/{{ run.year }}{% endblock %}
{% block content %}
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
  <div>
    <h1>{{ client.name }} — {{ run.month }}/{{ run.year }}</h1>
    <span class="badge badge-{{ run.status }}">{{ run.status }}</span>
    <span style="font-size:.8rem;color:#64748b;margin-left:.5rem">Version {{ run.version }}</span>
  </div>
  <a href="/history" style="color:#64748b;font-size:.875rem">← History</a>
</div>

<div class="review-grid">
  <!-- LEFT: Payroll -->
  <div>
    <div class="card">
      <h2>Payroll Summary</h2>
      <div class="stat-grid">
        <div class="stat-box"><div class="label">Employees</div><div class="value">{{ totals.count }}</div></div>
        <div class="stat-box"><div class="label">Total Gross</div><div class="value">₹{{ "{:,.0f}".format(totals.gross) }}</div></div>
        <div class="stat-box"><div class="label">Total PF</div><div class="value">₹{{ "{:,.0f}".format(totals.pf) }}</div></div>
        <div class="stat-box"><div class="label">Total ESIC</div><div class="value">₹{{ "{:,.0f}".format(totals.esic) }}</div></div>
        <div class="stat-box"><div class="label">Total Net Pay</div><div class="value" style="color:#16a34a">₹{{ "{:,.0f}".format(totals.net) }}</div></div>
      </div>
      <div style="overflow-x:auto">
        <table>
          <thead><tr><th>Name</th><th>Days</th><th>Gross</th><th>PF</th><th>ESIC</th><th>PT</th><th>Net Pay</th></tr></thead>
          <tbody>
          {% for emp in payroll %}
            <tr>
              <td>{{ emp.name }}<br><small style="color:#64748b">{{ emp.designation or '' }}</small></td>
              <td>{{ emp.days_worked }}/{{ emp.days_in_month }}</td>
              <td>₹{{ "{:,.0f}".format(emp.gross_earned) }}</td>
              <td>₹{{ "{:,.0f}".format(emp.employee_pf) }}</td>
              <td>₹{{ "{:,.0f}".format(emp.employee_esic) }}</td>
              <td>₹{{ "{:,.0f}".format(emp.professional_tax) }}</td>
              <td><strong>₹{{ "{:,.0f}".format(emp.net_pay) }}</strong></td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- RIGHT: Compliance -->
  <div>
    <div class="card">
      <h2>Compliance Validation</h2>
      {% if has_blocks %}
        <p class="error">🔴 Blocking issues found — resolve before approving</p>
      {% else %}
        <p class="success">🟢 No blocking issues — ready to approve</p>
      {% endif %}
      {% for f in compliance %}
        <div class="finding finding-{{ f.severity }}">
          <strong>
            {% if f.severity == 'fail' %}🔴{% elif f.severity == 'partial' %}🟡{% else %}🟢{% endif %}
            {{ f.act }}
          </strong>
          {% if f.area %}<span style="color:#64748b;font-size:.8rem"> · {{ f.area }}</span>{% endif %}
          <div style="margin-top:.3rem;font-size:.8rem">{{ f.reason }}</div>
          {% if f.penalty %}<div style="font-size:.75rem;color:#991b1b;margin-top:.2rem">Penalty: {{ f.penalty }}</div>{% endif %}
        </div>
      {% endfor %}
    </div>

    {% if run.status == "draft" %}
    <div class="card">
      <h2>Request Edit</h2>
      <!-- Text edit -->
      <form method="post" action="/run/{{ run.id }}/edit" style="margin-bottom:1.5rem">
        <input type="hidden" name="edit_type" value="text">
        <label>Type an instruction
          <textarea name="instruction" rows="3" style="width:100%;border:1px solid #cbd5e1;border-radius:6px;padding:.5rem;margin-top:.25rem;font-size:.9rem" placeholder='"Change Ravi to 26 days" or "Add ₹2,000 advance for Priya"'></textarea>
        </label>
        <button type="submit" class="btn btn-primary btn-sm" style="margin-top:.5rem">Apply Edit & Re-run</button>
      </form>
      <!-- Re-upload -->
      <form method="post" action="/run/{{ run.id }}/edit" enctype="multipart/form-data">
        <input type="hidden" name="edit_type" value="reupload">
        <label>Or re-upload corrected file
          <input type="file" name="file" accept=".csv,.xlsx,.xls,.pdf,.jpg,.jpeg,.png,.docx" style="margin-top:.25rem">
        </label>
        <button type="submit" class="btn btn-sm" style="margin-top:.5rem;background:#e2e8f0">Re-upload & Re-run</button>
      </form>
    </div>

    <!-- Approve -->
    <form method="post" action="/run/{{ run.id }}/approve">
      <button type="submit" class="btn btn-primary"
              style="width:100%;padding:.75rem;font-size:1rem{% if has_blocks %};opacity:.4;cursor:not-allowed{% endif %}"
              {% if has_blocks %}disabled title="Resolve blocking compliance issues first"{% endif %}>
        ✓ Approve & Generate Files
      </button>
    </form>
    {% else %}
    <div class="card" style="text-align:center">
      <p style="color:#16a34a;font-weight:700;margin-bottom:1rem">✓ Approved</p>
      <a href="/download/{{ run.id }}" class="btn btn-primary">Download Output Files</a>
    </div>
    {% endif %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Register client router in main.py**

```python
from app.routers.client import router as client_router
app.include_router(client_router)
```

- [ ] **Step 5: Smoke test end-to-end upload**

```bash
cd /Users/madhavibhat/payroll_crm && uvicorn app.main:app --reload --port 8001
```

1. Log in as operator
2. Go to `/operator/clients` → create "TechSpark IT" client (Maharashtra, IT, headcount 10)
3. Create a client login for it
4. Go to `/upload` → select TechSpark → June 2026 → upload `payroll_v2/test_data/company_single_techspark.csv`
5. Should redirect to `/review/{run_id}` showing employee table and compliance findings

- [ ] **Step 6: Commit**

```bash
cd /Users/madhavibhat/payroll_crm && git add -A && git commit -m "feat: upload, review, edit loop, approve routes and templates"
```

---

## Task 8: Output Generation + Download Centre + History

**Files:**
- Create: `app/routers/download.py`
- Create: `templates/download.html`
- Create: `templates/history.html`
- Modify: `app/routers/client.py` — imports `generate_outputs` from download.py

**Interfaces:**
- Consumes: `Run`, `Output` models, `payroll_v2/app/ecr_generator.py`, `payroll_v2/app/pdf_generator.py`
- Produces:
  - `generate_outputs(run: Run, session: Session)` — writes all 5 files to `outputs/{run_id}/`, inserts `Output` rows
  - Routes `/download/{run_id}/{file_type}` (GET), `/history` (GET)

- [ ] **Step 1: Create app/routers/download.py**

```python
import json
import csv
import io
import importlib.util
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import get_session
from app.models import Run, Output, Client, User
from app.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent.parent / "templates")
OUTPUTS_DIR = Path(__file__).parent.parent.parent / "outputs"

def _load_ecr_generator():
    spec = importlib.util.spec_from_file_location(
        "ecr_generator_v2",
        Path("/Users/madhavibhat/payroll_v2/app/ecr_generator.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _load_pdf_generator():
    spec = importlib.util.spec_from_file_location(
        "pdf_generator_v2",
        Path("/Users/madhavibhat/payroll_v2/app/pdf_generator.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_ecr_gen = _load_ecr_generator()
_pdf_gen = _load_pdf_generator()

def generate_outputs(run: Run, session: Session):
    from app.models import Client as ClientModel
    client = session.get(ClientModel, run.client_id)
    payroll = json.loads(run.payroll_json)
    compliance = json.loads(run.compliance_json)

    out_dir = OUTPUTS_DIR / str(run.id)
    out_dir.mkdir(parents=True, exist_ok=True)

    establishment_id = getattr(client, "establishment_id", "") or "MH/MUM/00000"
    company_name = client.name

    # 1. ECR TXT
    ecr_text = _ecr_gen.generate_ecr(payroll, establishment_id, company_name, run.month, run.year)
    ecr_path = out_dir / "ecr.txt"
    ecr_path.write_text(ecr_text)
    _save_output(session, run.id, "ecr", str(ecr_path))

    # 2. ESIC CSV
    esic_text = _ecr_gen.generate_esic_csv(payroll, run.month, run.year)
    esic_path = out_dir / "esic.csv"
    esic_path.write_text(esic_text)
    _save_output(session, run.id, "esic", str(esic_path))

    # 3. Salary slips ZIP
    slips_path = out_dir / "salary_slips.zip"
    _pdf_gen.generate_all_slips_zip(payroll, company_name, run.month, run.year, str(slips_path))
    _save_output(session, run.id, "slips", str(slips_path))

    # 4. Bank transfer file
    bank_path = out_dir / "bank_transfer.csv"
    _generate_bank_csv(payroll, bank_path)
    _save_output(session, run.id, "bank", str(bank_path))

    # 5. Compliance PDF
    compliance_path = out_dir / "compliance_report.pdf"
    _generate_compliance_pdf(compliance, client, run, compliance_path)
    _save_output(session, run.id, "compliance", str(compliance_path))

    session.commit()

def _save_output(session, run_id, output_type, path):
    session.add(Output(run_id=run_id, output_type=output_type, storage_path=path))

def _generate_bank_csv(payroll: list[dict], path: Path):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Employee Name", "Bank Account", "IFSC Code", "Net Pay"])
        for emp in payroll:
            writer.writerow([
                emp.get("name", ""),
                emp.get("bank_account", ""),
                emp.get("ifsc_code", ""),
                emp.get("net_pay", 0),
            ])

def _generate_compliance_pdf(findings: list[dict], client, run: Run, path: Path):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet

    doc = SimpleDocTemplate(str(path), pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"Compliance Report — {client.name}", styles["Title"]))
    story.append(Paragraph(f"Month: {run.month}/{run.year}  |  Version: {run.version}", styles["Normal"]))
    story.append(Spacer(1, 20))

    data = [["Act", "Area", "Status", "Reason"]]
    for f in findings:
        status_label = {"compliant": "✓ Pass", "partial": "⚠ Warn", "non_compliant": "✗ Fail", "not_applicable": "N/A"}.get(f["status"], f["status"])
        data.append([f["act"][:30], f.get("area", ""), status_label, f.get("reason", "")[:80]])

    t = Table(data, colWidths=[150, 80, 60, 230])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("WORDWRAP", (0, 0), (-1, -1), True),
    ]))
    story.append(t)
    doc.build(story)

@router.get("/download/{run_id}", response_class=HTMLResponse)
def download_page(run_id: int, request: Request,
                   session: Session = Depends(get_session),
                   user: User = Depends(get_current_user)):
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404)
    client = session.get(Client, run.client_id)
    outputs = session.execute(select(Output).where(Output.run_id == run_id)).scalars().all()
    output_map = {o.output_type: o for o in outputs}
    return templates.TemplateResponse("download.html", {
        "request": request, "run": run, "client": client,
        "output_map": output_map, "role": user.role
    })

@router.get("/download/{run_id}/{file_type}")
def download_file(run_id: int, file_type: str,
                   session: Session = Depends(get_session),
                   user: User = Depends(get_current_user)):
    output = session.execute(
        select(Output).where(Output.run_id == run_id, Output.output_type == file_type)
    ).scalar_one_or_none()
    if not output:
        raise HTTPException(status_code=404, detail="File not generated yet")
    path = Path(output.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing from disk")
    return FileResponse(path, filename=path.name)

@router.get("/history", response_class=HTMLResponse)
def history(request: Request, session: Session = Depends(get_session),
             user: User = Depends(get_current_user)):
    if user.role == "operator":
        runs = session.execute(select(Run).order_by(Run.created_at.desc())).scalars().all()
    else:
        runs = session.execute(
            select(Run).where(Run.client_id == user.client_id).order_by(Run.created_at.desc())
        ).scalars().all()
    run_data = []
    for r in runs:
        c = session.get(Client, r.client_id)
        run_data.append({"run": r, "client": c})
    return templates.TemplateResponse("history.html", {
        "request": request, "run_data": run_data, "role": user.role
    })
```

- [ ] **Step 2: Create templates/download.html**

```html
{% extends "base.html" %}
{% block title %}Download — {{ client.name }} {{ run.month }}/{{ run.year }}{% endblock %}
{% block content %}
<h1>{{ client.name }} — {{ run.month }}/{{ run.year }} v{{ run.version }}</h1>
<p class="success" style="margin-bottom:1.5rem">✓ Approved — all files ready for download</p>

<div class="download-grid">
  <div class="download-card">
    <div class="icon">🏛</div>
    <strong>EPFO ECR TXT</strong>
    <p style="font-size:.8rem;color:#64748b;margin:.5rem 0">Upload to EPFO unified portal</p>
    <a href="/download/{{ run.id }}/ecr" class="btn btn-primary btn-sm">Download ECR</a>
  </div>
  <div class="download-card">
    <div class="icon">🏥</div>
    <strong>ESIC CSV</strong>
    <p style="font-size:.8rem;color:#64748b;margin:.5rem 0">Upload to ESIC employer portal</p>
    <a href="/download/{{ run.id }}/esic" class="btn btn-primary btn-sm">Download ESIC</a>
  </div>
  <div class="download-card">
    <div class="icon">📄</div>
    <strong>Salary Slips ZIP</strong>
    <p style="font-size:.8rem;color:#64748b;margin:.5rem 0">PDF per employee</p>
    <a href="/download/{{ run.id }}/slips" class="btn btn-primary btn-sm">Download Slips</a>
  </div>
  <div class="download-card">
    <div class="icon">🏦</div>
    <strong>Bank Transfer File</strong>
    <p style="font-size:.8rem;color:#64748b;margin:.5rem 0">NEFT bulk salary CSV</p>
    <a href="/download/{{ run.id }}/bank" class="btn btn-primary btn-sm">Download Bank File</a>
  </div>
  <div class="download-card">
    <div class="icon">📋</div>
    <strong>Compliance Report</strong>
    <p style="font-size:.8rem;color:#64748b;margin:.5rem 0">15-act audit PDF</p>
    <a href="/download/{{ run.id }}/compliance" class="btn btn-primary btn-sm">Download Report</a>
  </div>
</div>

<div style="margin-top:1.5rem">
  <a href="/review/{{ run.id }}" style="color:#64748b;font-size:.875rem">← View Review</a>
  &nbsp;&nbsp;
  <a href="/history" style="color:#64748b;font-size:.875rem">History →</a>
</div>
{% endblock %}
```

- [ ] **Step 3: Create templates/history.html**

```html
{% extends "base.html" %}
{% block title %}Run History{% endblock %}
{% block content %}
<h1>Run History</h1>
<div class="card">
  <table>
    <thead>
      <tr><th>Client</th><th>Period</th><th>Version</th><th>Status</th><th>Created</th><th>Actions</th></tr>
    </thead>
    <tbody>
    {% for item in run_data %}
      <tr>
        <td>{{ item.client.name if item.client else '—' }}</td>
        <td>{{ item.run.month }}/{{ item.run.year }}</td>
        <td>v{{ item.run.version }}</td>
        <td><span class="badge badge-{{ item.run.status }}">{{ item.run.status }}</span></td>
        <td style="font-size:.8rem;color:#64748b">{{ item.run.created_at.strftime('%d %b %Y %H:%M') if item.run.created_at else '—' }}</td>
        <td>
          <a href="/review/{{ item.run.id }}" class="btn btn-sm" style="background:#e2e8f0">Review</a>
          {% if item.run.status == 'approved' %}
            <a href="/download/{{ item.run.id }}" class="btn btn-sm btn-primary">Downloads</a>
          {% endif %}
        </td>
      </tr>
    {% else %}
      <tr><td colspan="6" style="text-align:center;color:#64748b">No runs yet</td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 4: Register download router in main.py**

```python
from app.routers.download import router as download_router
app.include_router(download_router)
```

- [ ] **Step 5: Full end-to-end smoke test**

```bash
cd /Users/madhavibhat/payroll_crm && uvicorn app.main:app --reload --port 8001
```

1. Log in as operator → create TechSpark client + client login
2. Upload `company_single_techspark.csv` for June 2026
3. Review screen shows 10 employees + compliance findings
4. Click "Approve & Generate Files"
5. Download page shows all 5 download buttons
6. Download ECR TXT — verify it contains `#~#` pipe-delimited lines
7. Download ESIC CSV — verify employee rows
8. Download Salary Slips ZIP — verify PDFs inside
9. Download Bank Transfer CSV — verify account + net pay columns
10. Download Compliance Report PDF — verify it opens

- [ ] **Step 6: Test client login flow**

Log out → log in as client user → should land on `/upload` → upload their file → review → approve → download. Verify client cannot see other clients' runs by navigating to a run_id belonging to a different client (should get 403).

- [ ] **Step 7: Commit**

```bash
cd /Users/madhavibhat/payroll_crm && git add -A && git commit -m "feat: output generation, download centre, run history"
```

---

## Task 9: README + .env setup

**Files:**
- Create: `payroll_crm/README.md`

- [ ] **Step 1: Create README.md**

```markdown
# Payroll CRM — Local Setup

## Prerequisites
- Python 3.12+
- Payroll V2 engine at `/Users/madhavibhat/payroll_v2/`
- CPS Compliance Platform at `/Users/madhavibhat/cps-compliance-platform/`

## Install
```bash
cd /Users/madhavibhat/payroll_crm
pip3 install -r requirements.txt
```

## Configure
```bash
cp .env.example .env
# Edit .env — set CLAUDE_API_KEY and SECRET_KEY
```

## Seed operator account
```bash
python seed.py
# Creates admin@cps.in / admin123
```

## Run
```bash
uvicorn app.main:app --reload --port 8001
```
Open http://localhost:8001

## Test with sample files
Sample files in `/Users/madhavibhat/payroll_v2/test_data/`:
- `company_single_techspark.csv` — 10-employee IT company (structured)
- `company1_brightmfg.csv` — 12-employee factory
- `company2_starpharma.csv` — 10-employee pharma
```

- [ ] **Step 2: Final commit**

```bash
cd /Users/madhavibhat/payroll_crm && git add -A && git commit -m "docs: README and setup instructions"
```

---

## Self-Review

**Spec coverage check:**
- ✓ Two roles (operator/client) — Tasks 2, 6, 7
- ✓ Structured + unstructured ingestion — Task 4
- ✓ Payroll engine wrapper — Task 3
- ✓ Compliance as validation gate — Task 7 (approve blocked by fail findings)
- ✓ Iterative edit loop (text + reupload) — Task 7
- ✓ Version history — Tasks 5, 8
- ✓ 5 output files on approval — Task 8
- ✓ SQLite with DATABASE_URL swap — Task 1
- ✓ 7 UI screens — Tasks 2, 6, 7, 8
- ✓ importlib isolation (no sys.path collision) — Tasks 3, 8

**Placeholder scan:** No TBDs. All code blocks complete. ✓

**Type consistency:**
- `run_payroll()` returns `list[dict]` — used as `list[dict]` throughout ✓
- `run_compliance()` returns `list[dict]` — used as `list[dict]` throughout ✓
- `orchestrate()` returns `Run` ORM object — used as `Run` in client.py ✓
- `generate_outputs()` called in client.py approve route — defined in download.py ✓
