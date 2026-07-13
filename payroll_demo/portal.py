"""
CPS LLP Payroll Management Portal
Roles: CPS Admin | Employer | Employee
Run: uvicorn portal:app --reload --port 8001
"""

import hashlib
import hmac
import io
import os
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer,
    LargeBinary, String, create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship, sessionmaker
import pandas as pd

from ecr_generator import generate_ecr, generate_esic_csv
from payroll_engine import EmployeeInput, MONTH_NAMES, calculate_payroll
from pdf_generator import generate_salary_slip_pdf

# ══════════════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════════════
SECRET_KEY  = "cps-llp-portal-secret-2024"
ALGORITHM   = "HS256"
TOKEN_HOURS = 8

# ══════════════════════════════════════════════════════════════════════════════
# Database
# ══════════════════════════════════════════════════════════════════════════════
DATABASE_URL = "sqlite:///./payroll_portal.db"
engine       = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()
_HASH_SALT   = "cps-llp-2024"


class Company(Base):
    __tablename__    = "companies"
    id               = Column(Integer, primary_key=True)
    name             = Column(String(200), nullable=False)
    establishment_id = Column(String(50))
    address          = Column(String(500))
    contact_email    = Column(String(200))
    industry         = Column(String(100))
    created_at       = Column(DateTime, default=datetime.utcnow)
    users            = relationship("User", back_populates="company")
    payroll_runs     = relationship("PayrollRun", back_populates="company",
                                   order_by="PayrollRun.created_at.desc()")
    documents        = relationship("Document", back_populates="company")


class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True)
    email         = Column(String(200), unique=True, nullable=False)
    name          = Column(String(200), nullable=False)
    password_hash = Column(String(200), nullable=False)
    role          = Column(String(20), nullable=False)  # cps | employer | employee
    company_id    = Column(Integer, ForeignKey("companies.id"), nullable=True)
    emp_id        = Column(String(50), nullable=True)
    department    = Column(String(100))
    designation   = Column(String(100))
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    company       = relationship("Company", back_populates="users")
    documents     = relationship("Document", back_populates="employee_user")


class PayrollRun(Base):
    __tablename__      = "payroll_runs"
    id                 = Column(Integer, primary_key=True)
    company_id         = Column(Integer, ForeignKey("companies.id"))
    month              = Column(Integer, nullable=False)
    year               = Column(Integer, nullable=False)
    status             = Column(String(20), default="processed")
    total_employees    = Column(Integer, default=0)
    total_gross        = Column(Float, default=0)
    total_net          = Column(Float, default=0)
    total_pf_challan   = Column(Float, default=0)
    total_esic_challan = Column(Float, default=0)
    created_at         = Column(DateTime, default=datetime.utcnow)
    company            = relationship("Company", back_populates="payroll_runs")
    documents          = relationship("Document", back_populates="payroll_run")


class Document(Base):
    __tablename__  = "documents"
    id             = Column(Integer, primary_key=True)
    doc_type       = Column(String(50), nullable=False)
    name           = Column(String(200), nullable=False)
    company_id     = Column(Integer, ForeignKey("companies.id"))
    employee_id    = Column(Integer, ForeignKey("users.id"), nullable=True)
    payroll_run_id = Column(Integer, ForeignKey("payroll_runs.id"), nullable=True)
    file_data      = Column(LargeBinary)
    month          = Column(Integer, nullable=True)
    year           = Column(Integer, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    company        = relationship("Company", back_populates="documents")
    employee_user  = relationship("User", back_populates="documents")
    payroll_run    = relationship("PayrollRun", back_populates="documents")


# ══════════════════════════════════════════════════════════════════════════════
# Auth helpers
# ══════════════════════════════════════════════════════════════════════════════

def hash_pw(pw: str) -> str:
    return hashlib.sha256((_HASH_SALT + pw).encode()).hexdigest()

def verify_pw(pw: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_pw(pw), hashed)

def create_token(email: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": email, "role": role, "exp": expire},
                      SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    data = decode_token(token)
    if not data:
        return None
    return db.query(User).filter(
        User.email == data.get("sub"), User.is_active == True
    ).first()


# ══════════════════════════════════════════════════════════════════════════════
# Seed data
# ══════════════════════════════════════════════════════════════════════════════

TECHCORP_EMP_DATA = [
    dict(emp_id="TC001", name="Rajesh Kumar",  uan="101234567890",
         pf_number="MH/MUM/12345/001", esic_number="4100234567",
         basic=45000, da=4500, hra=18000, other=7500,
         designation="Senior Software Engineer", department="Engineering",
         bank_account="37891234567890", ifsc_code="HDFC0001234"),
    dict(emp_id="TC002", name="Priya Sharma",  uan="101234567891",
         pf_number="MH/MUM/12345/002", esic_number="4100234568",
         basic=35000, da=3500, hra=14000, other=5500,
         designation="Marketing Manager", department="Marketing",
         bank_account="37891234567891", ifsc_code="HDFC0001234"),
    dict(emp_id="TC003", name="Amit Joshi",    uan="101234567892",
         pf_number="MH/MUM/12345/003", esic_number="4100234569",
         basic=18000, da=1800, hra=7200,  other=3000,
         designation="Junior Developer", department="Engineering",
         bank_account="37891234567892", ifsc_code="HDFC0001234"),
    dict(emp_id="TC004", name="Deepa Verma",   uan="101234567893",
         pf_number="MH/MUM/12345/004", esic_number="4100234570",
         basic=28000, da=2800, hra=11200, other=4000,
         designation="Finance Analyst", department="Finance",
         bank_account="37891234567893", ifsc_code="HDFC0001234"),
    dict(emp_id="TC005", name="Ravi Krishnan", uan="101234567894",
         pf_number="MH/MUM/12345/005", esic_number="4100234571",
         basic=38000, da=3800, hra=15200, other=6000,
         designation="Operations Lead", department="Operations",
         bank_account="37891234567894", ifsc_code="HDFC0001234"),
]

BUILDMART_EMP_DATA = [
    dict(emp_id="BM001", name="Sanjay Raut",   uan="201234567890",
         pf_number="MH/PUN/67890/001", esic_number="4200234567",
         basic=22000, da=2200, hra=8800,  other=3500,
         designation="Site Engineer", department="Civil",
         bank_account="47891234567890", ifsc_code="SBIN0000123"),
    dict(emp_id="BM002", name="Kavita Desai",  uan="201234567891",
         pf_number="MH/PUN/67890/002", esic_number="4200234568",
         basic=30000, da=3000, hra=12000, other=4500,
         designation="Project Manager", department="Projects",
         bank_account="47891234567891", ifsc_code="SBIN0000123"),
    dict(emp_id="BM003", name="Mohan Shinde",  uan="201234567892",
         pf_number="MH/PUN/67890/003", esic_number="4200234569",
         basic=16000, da=1600, hra=6400,  other=2500,
         designation="Supervisor", department="Operations",
         bank_account="47891234567892", ifsc_code="SBIN0000123"),
]


def seed_db(db: Session):
    if db.query(User).filter(User.email == "admin@cpsllp.com").first():
        return

    # ── Companies ──────────────────────────────────────────────────────────
    techcorp = Company(
        name="Techcorp Pvt Ltd", establishment_id="MH/MUM/12345",
        address="5th Floor, Cyber City, Hiranandani Estate, Thane, Maharashtra 400607",
        contact_email="hr@techcorp.com", industry="Information Technology",
    )
    buildmart = Company(
        name="Buildmart Industries Ltd", establishment_id="MH/PUN/67890",
        address="Plot 42, MIDC Bhosari, Pune, Maharashtra 411026",
        contact_email="hr@buildmart.in", industry="Construction",
    )
    db.add_all([techcorp, buildmart])
    db.flush()

    # ── Users ──────────────────────────────────────────────────────────────
    cps_admin = User(email="admin@cpsllp.com", name="Vikram Mehta",
                     password_hash=hash_pw("CPS@2024"), role="cps")
    hr_tc = User(email="hr@techcorp.com", name="Anita Kapoor",
                 password_hash=hash_pw("Techcorp@2024"), role="employer",
                 company_id=techcorp.id, designation="HR Manager", department="HR")
    hr_bm = User(email="hr@buildmart.in", name="Suresh Patil",
                 password_hash=hash_pw("Buildmart@2024"), role="employer",
                 company_id=buildmart.id, designation="HR Manager", department="HR")
    db.add_all([cps_admin, hr_tc, hr_bm])
    db.flush()

    emp_users_tc = {}
    for e in TECHCORP_EMP_DATA:
        first = e["name"].split()[0].lower()
        last  = e["name"].split()[1].lower() if len(e["name"].split()) > 1 else ""
        u = User(
            email=f"{first}.{last}@techcorp.com",
            name=e["name"], password_hash=hash_pw(e["name"].split()[0] + "@2024"),
            role="employee", company_id=techcorp.id,
            emp_id=e["emp_id"], department=e["department"], designation=e["designation"],
        )
        db.add(u)
    db.flush()
    for e in TECHCORP_EMP_DATA:
        emp_users_tc[e["emp_id"]] = db.query(User).filter(User.emp_id == e["emp_id"]).first()

    emp_users_bm = {}
    for e in BUILDMART_EMP_DATA:
        first = e["name"].split()[0].lower()
        last  = e["name"].split()[1].lower() if len(e["name"].split()) > 1 else ""
        u = User(
            email=f"{first}.{last}@buildmart.in",
            name=e["name"], password_hash=hash_pw(e["name"].split()[0] + "@2024"),
            role="employee", company_id=buildmart.id,
            emp_id=e["emp_id"], department=e["department"], designation=e["designation"],
        )
        db.add(u)
    db.flush()
    for e in BUILDMART_EMP_DATA:
        emp_users_bm[e["emp_id"]] = db.query(User).filter(User.emp_id == e["emp_id"]).first()

    # ── Payroll runs ────────────────────────────────────────────────────────
    def _make_run(company, emp_data, emp_users, month, year, status):
        emps = [
            EmployeeInput(
                emp_id=e["emp_id"], name=e["name"], uan=e["uan"],
                pf_number=e["pf_number"], esic_number=e["esic_number"],
                basic=e["basic"], da=e["da"], hra=e["hra"],
                other_allowances=e["other"], days_in_month=30, days_worked=30,
                bank_account=e["bank_account"], ifsc_code=e["ifsc_code"],
                designation=e["designation"], department=e["department"],
            )
            for e in emp_data
        ]
        results = [calculate_payroll(emp, month, year) for emp in emps]

        run = PayrollRun(
            company_id=company.id, month=month, year=year, status=status,
            total_employees=len(results),
            total_gross=sum(r.gross_earned for r in results),
            total_net=sum(r.net_pay for r in results),
            total_pf_challan=sum(r.employee_pf + r.employer_epf + r.employer_eps for r in results),
            total_esic_challan=sum(r.employee_esic + r.employer_esic for r in results),
        )
        db.add(run)
        db.flush()

        ecr_text  = generate_ecr(results, company.establishment_id, company.name, month, year)
        esic_text = generate_esic_csv(results, month, year)

        bank_rows = ["SL_NO,NAME,ACCOUNT,IFSC,NET_AMOUNT,REFERENCE"]
        for i, r in enumerate(results, 1):
            bank_rows.append(
                f"{i},{r.name},{r.bank_account},{r.ifsc_code},"
                f"{int(r.net_pay)},SAL/{year}/{month:02d}/{r.emp_id}"
            )
        reg_rows = ["EMP_ID,NAME,GROSS,NET,EMP_PF,ER_PF,EMP_ESIC,ER_ESIC,PT,ADVANCE"]
        for r in results:
            reg_rows.append(
                f"{r.emp_id},{r.name},{int(r.gross_earned)},{int(r.net_pay)},"
                f"{int(r.employee_pf)},{int(r.employer_epf+r.employer_eps)},"
                f"{int(r.employee_esic)},{int(r.employer_esic)},"
                f"{int(r.professional_tax)},{int(r.advance_deduction)}"
            )

        db.add(Document(doc_type="ecr",
                        name=f"ECR_PF_{MONTH_NAMES[month]}_{year}.txt",
                        company_id=company.id, payroll_run_id=run.id,
                        file_data=ecr_text.encode(), month=month, year=year))
        db.add(Document(doc_type="esic",
                        name=f"ESIC_Contribution_{MONTH_NAMES[month]}_{year}.csv",
                        company_id=company.id, payroll_run_id=run.id,
                        file_data=esic_text.encode(), month=month, year=year))
        db.add(Document(doc_type="bank_advice",
                        name=f"BankAdvice_{MONTH_NAMES[month]}_{year}.csv",
                        company_id=company.id, payroll_run_id=run.id,
                        file_data="\n".join(bank_rows).encode(), month=month, year=year))
        db.add(Document(doc_type="payroll_register",
                        name=f"PayrollRegister_{MONTH_NAMES[month]}_{year}.csv",
                        company_id=company.id, payroll_run_id=run.id,
                        file_data="\n".join(reg_rows).encode(), month=month, year=year))

        for r in results:
            pdf = generate_salary_slip_pdf(r, month, year, company.name)
            eu  = emp_users.get(r.emp_id)
            db.add(Document(doc_type="salary_slip",
                            name=f"SalarySlip_{r.emp_id}_{MONTH_NAMES[month]}_{year}.pdf",
                            company_id=company.id, payroll_run_id=run.id,
                            employee_id=eu.id if eu else None,
                            file_data=pdf, month=month, year=year))

    # Techcorp: Jan–Mar 2025
    for m, st in [(1, "disbursed"), (2, "disbursed"), (3, "processed")]:
        _make_run(techcorp, TECHCORP_EMP_DATA, emp_users_tc, m, 2025, st)

    # Buildmart: Feb–Mar 2025
    for m, st in [(2, "disbursed"), (3, "processed")]:
        _make_run(buildmart, BUILDMART_EMP_DATA, emp_users_bm, m, 2025, st)

    db.commit()
    print("✅ Portal database seeded with demo data")


# ══════════════════════════════════════════════════════════════════════════════
# Payroll CSV helper (for CPS run-payroll page)
# ══════════════════════════════════════════════════════════════════════════════

COL_ALIASES = {
    "emp_id":   ["emp_id","employee_id","empid","id","emp_code","sr_no"],
    "name":     ["name","employee_name","emp_name","full_name","employee"],
    "uan":      ["uan","uan_number","universal_account_number"],
    "pf_number":["pf_number","pf_no","pf_account","epf_number"],
    "esic_number":["esic_number","esic_no","ip_number","esic"],
    "basic":    ["basic","basic_salary","basic_pay","basic_wages","base_salary"],
    "da":       ["da","dearness_allowance","dearness_allow","da_amount"],
    "hra":      ["hra","house_rent_allowance","house_rent","hra_amount"],
    "other_allowances":["other_allowances","other","special_allowance","conveyance","misc_allowance"],
    "days_in_month":["days_in_month","total_days","calendar_days","month_days"],
    "days_worked":["days_worked","days_present","present_days","paid_days","attendance_days"],
    "advance_deduction":["advance_deduction","advance","loan_deduction","recovery"],
    "bank_account":["bank_account","account_number","bank_acc","acc_no","account_no"],
    "ifsc_code":["ifsc_code","ifsc","bank_ifsc","bank_code"],
    "designation":["designation","role","position","job_title","title"],
    "department":["department","dept","division","section","cost_centre"],
}

def _find_col(df, field):
    cols = df.columns.tolist()
    for alias in COL_ALIASES[field]:
        if alias in cols:
            return alias
    for col in cols:
        for alias in COL_ALIASES[field]:
            if alias in col or col in alias:
                return col
    return None

def _get(row, df, field, default=0):
    col = _find_col(df, field)
    if col is None:
        return default
    val = row.get(col, default)
    return val if pd.notna(val) else default

def _parse_file(content: bytes, filename: str):
    if filename.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    else:
        df = pd.read_excel(io.BytesIO(content))
    df.columns = [
        str(c).strip().lower().replace(" ","_").replace("-","_").replace(".","_")
        for c in df.columns
    ]
    return df

def _build_employees(df) -> List[EmployeeInput]:
    employees = []
    for _, row in df.iterrows():
        basic = float(_get(row, df, "basic", 0))
        da    = float(_get(row, df, "da",    0))
        hra   = float(_get(row, df, "hra",   0))
        other = float(_get(row, df, "other_allowances", 0))
        if basic == da == hra == other == 0:
            gross_col = next((c for c in df.columns if "gross" in c), None)
            if gross_col:
                g     = float(row.get(gross_col, 0) or 0)
                basic = round(g * 0.50)
                hra   = round(g * 0.30)
                other = round(g * 0.20)
        employees.append(EmployeeInput(
            emp_id=str(_get(row, df, "emp_id", "N/A")),
            name=str(_get(row, df, "name", "Unknown")),
            uan=str(_get(row, df, "uan", "")),
            pf_number=str(_get(row, df, "pf_number", "")),
            esic_number=str(_get(row, df, "esic_number", "")),
            basic=basic, da=da, hra=hra, other_allowances=other,
            days_in_month=int(_get(row, df, "days_in_month", 30)),
            days_worked=int(_get(row, df, "days_worked", 30)),
            advance_deduction=float(_get(row, df, "advance_deduction", 0)),
            bank_account=str(_get(row, df, "bank_account", "")),
            ifsc_code=str(_get(row, df, "ifsc_code", "")),
            designation=str(_get(row, df, "designation", "")),
            department=str(_get(row, df, "department", "")),
        ))
    return employees


# ══════════════════════════════════════════════════════════════════════════════
# App
# ══════════════════════════════════════════════════════════════════════════════

app       = FastAPI(title="CPS LLP Payroll Portal")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_db(db)
    finally:
        db.close()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _login_redirect():
    return RedirectResponse("/portal/login", status_code=302)

def _role_ctx(user: User) -> dict:
    return {
        "user": user,
        "role_label": {"cps": "CPS Admin", "employer": "Employer", "employee": "Employee"}.get(user.role, user.role),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Auth routes
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/portal", response_class=HTMLResponse)
async def portal_root(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return _login_redirect()
    return RedirectResponse(f"/portal/{user.role}", status_code=302)


@app.get("/portal/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(f"/portal/{user.role}", status_code=302)
    return templates.TemplateResponse("portal/login.html", {"request": request, "error": None})


@app.post("/portal/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email, User.is_active == True).first()
    if not user or not verify_pw(password, user.password_hash):
        return templates.TemplateResponse(
            "portal/login.html",
            {"request": request, "error": "Invalid email or password"},
            status_code=401,
        )
    token = create_token(user.email, user.role)
    resp  = RedirectResponse(f"/portal/{user.role}", status_code=302)
    resp.set_cookie("access_token", token, httponly=True, max_age=TOKEN_HOURS * 3600)
    return resp


@app.get("/portal/logout")
async def logout():
    resp = RedirectResponse("/portal/login", status_code=302)
    resp.delete_cookie("access_token")
    return resp


# ══════════════════════════════════════════════════════════════════════════════
# CPS Admin routes
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/portal/cps", response_class=HTMLResponse)
async def cps_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "cps":
        return _login_redirect()

    companies  = db.query(Company).all()
    total_emps = db.query(User).filter(User.role == "employee").count()
    all_runs   = db.query(PayrollRun).order_by(PayrollRun.created_at.desc()).limit(10).all()

    return templates.TemplateResponse("portal/cps_dashboard.html", {
        "request":    request,
        **_role_ctx(user),
        "companies":  companies,
        "total_emps": total_emps,
        "recent_runs": all_runs,
        "month_names": MONTH_NAMES,
    })


@app.get("/portal/cps/run-payroll", response_class=HTMLResponse)
async def cps_run_payroll_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "cps":
        return _login_redirect()
    companies = db.query(Company).all()
    return templates.TemplateResponse("portal/cps_run_payroll.html", {
        "request":   request,
        **_role_ctx(user),
        "companies": companies,
        "month_names": MONTH_NAMES,
    })


@app.post("/portal/cps/run-payroll", response_class=HTMLResponse)
async def cps_run_payroll_post(
    request: Request,
    file: UploadFile = File(...),
    company_id: int = Form(...),
    month: int = Form(...),
    year: int = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.role != "cps":
        return _login_redirect()

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    try:
        content  = await file.read()
        df       = _parse_file(content, file.filename)
        emps     = _build_employees(df)
        results  = [calculate_payroll(e, month, year) for e in emps]

        ecr_text  = generate_ecr(results, company.establishment_id, company.name, month, year)
        esic_text = generate_esic_csv(results, month, year)

        run = PayrollRun(
            company_id=company.id, month=month, year=year, status="processed",
            total_employees=len(results),
            total_gross=sum(r.gross_earned for r in results),
            total_net=sum(r.net_pay for r in results),
            total_pf_challan=sum(r.employee_pf + r.employer_epf + r.employer_eps for r in results),
            total_esic_challan=sum(r.employee_esic + r.employer_esic for r in results),
        )
        db.add(run)
        db.flush()

        bank_rows = ["SL_NO,NAME,ACCOUNT,IFSC,NET_AMOUNT,REFERENCE"]
        for i, r in enumerate(results, 1):
            bank_rows.append(
                f"{i},{r.name},{r.bank_account},{r.ifsc_code},"
                f"{int(r.net_pay)},SAL/{year}/{month:02d}/{r.emp_id}"
            )
        reg_rows = ["EMP_ID,NAME,GROSS,NET,EMP_PF,ER_PF,EMP_ESIC,ER_ESIC,PT,ADVANCE"]
        for r in results:
            reg_rows.append(
                f"{r.emp_id},{r.name},{int(r.gross_earned)},{int(r.net_pay)},"
                f"{int(r.employee_pf)},{int(r.employer_epf+r.employer_eps)},"
                f"{int(r.employee_esic)},{int(r.employer_esic)},"
                f"{int(r.professional_tax)},{int(r.advance_deduction)}"
            )

        db.add(Document(doc_type="ecr",
                        name=f"ECR_PF_{MONTH_NAMES[month]}_{year}.txt",
                        company_id=company.id, payroll_run_id=run.id,
                        file_data=ecr_text.encode(), month=month, year=year))
        db.add(Document(doc_type="esic",
                        name=f"ESIC_{MONTH_NAMES[month]}_{year}.csv",
                        company_id=company.id, payroll_run_id=run.id,
                        file_data=esic_text.encode(), month=month, year=year))
        db.add(Document(doc_type="bank_advice",
                        name=f"BankAdvice_{MONTH_NAMES[month]}_{year}.csv",
                        company_id=company.id, payroll_run_id=run.id,
                        file_data="\n".join(bank_rows).encode(), month=month, year=year))
        db.add(Document(doc_type="payroll_register",
                        name=f"PayrollRegister_{MONTH_NAMES[month]}_{year}.csv",
                        company_id=company.id, payroll_run_id=run.id,
                        file_data="\n".join(reg_rows).encode(), month=month, year=year))

        for r in results:
            pdf     = generate_salary_slip_pdf(r, month, year, company.name)
            emp_usr = db.query(User).filter(
                User.emp_id == r.emp_id, User.company_id == company.id
            ).first()
            db.add(Document(doc_type="salary_slip",
                            name=f"SalarySlip_{r.emp_id}_{MONTH_NAMES[month]}_{year}.pdf",
                            company_id=company.id, payroll_run_id=run.id,
                            employee_id=emp_usr.id if emp_usr else None,
                            file_data=pdf, month=month, year=year))

        db.commit()

        return templates.TemplateResponse("portal/cps_run_result.html", {
            "request":     request,
            **_role_ctx(user),
            "run":         run,
            "results":     results,
            "company":     company,
            "month_names": MONTH_NAMES,
            "month":       month,
            "year":        year,
        })

    except Exception as exc:
        import traceback
        return HTMLResponse(
            f"<div style='font-family:sans-serif;padding:2rem'>"
            f"<h2 style='color:red'>Error</h2><p>{exc}</p>"
            f"<pre>{traceback.format_exc()}</pre>"
            f"<a href='/portal/cps/run-payroll'>← Try again</a></div>",
            status_code=400,
        )


# ══════════════════════════════════════════════════════════════════════════════
# Employer routes
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/portal/employer", response_class=HTMLResponse)
async def employer_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "employer":
        return _login_redirect()

    company    = user.company
    runs       = db.query(PayrollRun).filter(PayrollRun.company_id == company.id)\
                    .order_by(PayrollRun.created_at.desc()).limit(6).all()
    emp_count  = db.query(User).filter(
        User.company_id == company.id, User.role == "employee"
    ).count()
    employees  = db.query(User).filter(
        User.company_id == company.id, User.role == "employee"
    ).all()

    return templates.TemplateResponse("portal/employer_dashboard.html", {
        "request":     request,
        **_role_ctx(user),
        "company":     company,
        "runs":        runs,
        "emp_count":   emp_count,
        "employees":   employees,
        "month_names": MONTH_NAMES,
    })


@app.get("/portal/employer/documents", response_class=HTMLResponse)
async def employer_documents(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "employer":
        return _login_redirect()

    company = user.company
    docs    = db.query(Document).filter(Document.company_id == company.id)\
                .order_by(Document.created_at.desc()).all()

    # Group by payroll run
    runs_with_docs = {}
    for doc in docs:
        rid = doc.payroll_run_id or "ungrouped"
        if rid not in runs_with_docs:
            runs_with_docs[rid] = {"run": doc.payroll_run, "docs": []}
        runs_with_docs[rid]["docs"].append(doc)

    return templates.TemplateResponse("portal/employer_documents.html", {
        "request":       request,
        **_role_ctx(user),
        "company":       company,
        "runs_with_docs": list(runs_with_docs.values()),
        "month_names":   MONTH_NAMES,
        "doc_type_labels": {
            "salary_slip":      "Salary Slip",
            "ecr":              "ECR / PF File",
            "esic":             "ESIC File",
            "bank_advice":      "Bank Payment Advice",
            "payroll_register": "Payroll Register",
            "challan":          "Challan Confirmation",
            "audit_report":     "Audit Report",
            "form16":           "Form 16",
        },
    })


@app.get("/portal/employer/compliance", response_class=HTMLResponse)
async def employer_compliance(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "employer":
        return _login_redirect()

    company = user.company
    runs    = db.query(PayrollRun).filter(PayrollRun.company_id == company.id)\
                .order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).all()

    return templates.TemplateResponse("portal/employer_compliance.html", {
        "request":     request,
        **_role_ctx(user),
        "company":     company,
        "runs":        runs,
        "month_names": MONTH_NAMES,
    })


# ══════════════════════════════════════════════════════════════════════════════
# Employee routes
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/portal/employee", response_class=HTMLResponse)
async def employee_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "employee":
        return _login_redirect()

    slips = db.query(Document).filter(
        Document.employee_id == user.id,
        Document.doc_type == "salary_slip",
    ).order_by(Document.year.desc(), Document.month.desc()).limit(3).all()

    # YTD for current year
    ytd_slips = db.query(Document).join(PayrollRun).filter(
        Document.employee_id == user.id,
        Document.doc_type == "salary_slip",
        Document.year == 2025,
    ).all()
    ytd_gross = 0
    ytd_net   = 0
    # We can't easily derive these from raw PDF, so use run totals proportionally
    runs = db.query(PayrollRun).filter(
        PayrollRun.company_id == user.company_id,
        PayrollRun.year == 2025,
    ).all()
    emp_count = db.query(User).filter(
        User.company_id == user.company_id, User.role == "employee"
    ).count() or 1
    ytd_gross = sum(r.total_gross / emp_count for r in runs)
    ytd_net   = sum(r.total_net   / emp_count for r in runs)

    # Latest run
    latest_run = db.query(PayrollRun).filter(
        PayrollRun.company_id == user.company_id
    ).order_by(PayrollRun.created_at.desc()).first()

    return templates.TemplateResponse("portal/employee_dashboard.html", {
        "request":    request,
        **_role_ctx(user),
        "company":    user.company,
        "slips":      slips,
        "ytd_gross":  ytd_gross,
        "ytd_net":    ytd_net,
        "latest_run": latest_run,
        "month_names": MONTH_NAMES,
    })


@app.get("/portal/employee/payslips", response_class=HTMLResponse)
async def employee_payslips(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "employee":
        return _login_redirect()

    slips = db.query(Document).filter(
        Document.employee_id == user.id,
        Document.doc_type == "salary_slip",
    ).order_by(Document.year.desc(), Document.month.desc()).all()

    return templates.TemplateResponse("portal/employee_payslips.html", {
        "request":     request,
        **_role_ctx(user),
        "company":     user.company,
        "slips":       slips,
        "month_names": MONTH_NAMES,
    })


@app.get("/portal/employee/ytd", response_class=HTMLResponse)
async def employee_ytd(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "employee":
        return _login_redirect()

    runs = db.query(PayrollRun).filter(
        PayrollRun.company_id == user.company_id,
        PayrollRun.year == 2025,
    ).order_by(PayrollRun.month).all()
    emp_count = db.query(User).filter(
        User.company_id == user.company_id, User.role == "employee"
    ).count() or 1

    monthly = []
    for r in runs:
        monthly.append({
            "month": MONTH_NAMES[r.month],
            "gross": round(r.total_gross / emp_count),
            "net":   round(r.total_net   / emp_count),
            "pf":    round(r.total_pf_challan / emp_count),
            "esic":  round(r.total_esic_challan / emp_count),
        })

    return templates.TemplateResponse("portal/employee_ytd.html", {
        "request": request,
        **_role_ctx(user),
        "company": user.company,
        "monthly": monthly,
    })


# ══════════════════════════════════════════════════════════════════════════════
# Document download
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/portal/download/{doc_id}")
async def download_document(doc_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return _login_redirect()

    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    # Access control
    if user.role == "employee" and doc.employee_id != user.id:
        raise HTTPException(403, "Access denied")
    if user.role == "employer" and doc.company_id != user.company_id:
        raise HTTPException(403, "Access denied")

    ext      = doc.name.rsplit(".", 1)[-1].lower()
    mime_map = {"pdf": "application/pdf", "txt": "text/plain",
                "csv": "text/csv", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    mime = mime_map.get(ext, "application/octet-stream")

    return StreamingResponse(
        io.BytesIO(doc.file_data),
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{doc.name}"'},
    )
