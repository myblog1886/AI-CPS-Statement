"""
New Labour Codes Compliant Payroll Tool
FastAPI application — run on port 8002:
  uvicorn lc_main:app --reload --port 8002

Mirrors structure of CPS LLP payroll tool (main.py / portal.py) but
purpose-built for the four Labour Codes 2019-2020:
  - Code on Wages 2019
  - Code on Social Security 2020
  - Industrial Relations Code 2020
  - Occupational Safety, Health & Working Conditions Code 2020
"""
import io
import uuid
import zipfile
from datetime import date
from typing import Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from lc_engine import (
    EmployeeInputLC, PayrollResultLC, MONTH_NAMES,
    calculate_payroll_lc, build_summary_lc,
)
from lc_ecr import generate_ecr_lc, generate_esic_csv_lc
from lc_pdf import generate_salary_slip_lc_pdf

app = FastAPI(title="New Labour Codes Compliant Payroll Tool")
templates = Jinja2Templates(directory="templates/lc")

SESSIONS: Dict[str, dict] = {}

# ── Column aliases (superset of legacy tool + new Labour Code columns) ────────
COL_ALIASES = {
    "emp_id":             ["emp_id", "employee_id", "empid", "id", "sr_no", "emp_code"],
    "name":               ["name", "employee_name", "emp_name", "full_name"],
    "uan":                ["uan", "uan_number", "uan_no"],
    "pf_number":          ["pf_number", "pf_no", "pf_account", "epf_number"],
    "esic_number":        ["esic_number", "esic_no", "ip_number"],
    "basic":              ["basic", "basic_salary", "basic_pay", "basic_wages", "bs"],
    "da":                 ["da", "dearness_allowance", "dearness_allow", "da_amount"],
    "hra":                ["hra", "house_rent_allowance", "house_rent", "hra_amount"],
    "special_allowance":  ["special_allowance", "special_allow", "special_pay",
                           "supplementary_allowance", "fixed_allowance"],
    "other_allowances":   ["other_allowances", "other", "conveyance",
                           "medical_allowance", "transport_allowance", "misc_allowance"],
    "ctc_monthly":        ["ctc_monthly", "ctc", "monthly_ctc", "cost_to_company",
                           "gross_ctc", "total_ctc"],
    "days_in_month":      ["days_in_month", "total_days", "calendar_days", "month_days"],
    "days_worked":        ["days_worked", "days_present", "present_days",
                           "actual_days", "paid_days"],
    "employment_type":    ["employment_type", "emp_type", "contract_type",
                           "employee_type", "type"],
    "years_of_service":   ["years_of_service", "years_service", "service_years",
                           "tenure_years", "years"],
    "ot_hours_month":     ["ot_hours_month", "ot_hours", "overtime_hours",
                           "ot_hrs", "overtime_hrs"],
    "daily_avg_hours":    ["daily_avg_hours", "avg_hours_per_day", "daily_hours",
                           "hours_per_day", "avg_daily_hours"],
    "leave_balance":      ["leave_balance", "leave_balance_opening", "el_balance",
                           "opening_leave", "leave_opening"],
    "advance_deduction":  ["advance_deduction", "advance", "loan_deduction",
                           "loan_recovery", "advance_recovery"],
    "bank_account":       ["bank_account", "account_number", "bank_acc", "acc_no"],
    "ifsc_code":          ["ifsc_code", "ifsc", "bank_ifsc"],
    "designation":        ["designation", "role", "position", "job_title", "title"],
    "department":         ["department", "dept", "division", "section"],
}


def _find_col(df: pd.DataFrame, field: str) -> Optional[str]:
    cols = df.columns.tolist()
    for alias in COL_ALIASES[field]:
        if alias in cols:
            return alias
    for col in cols:
        for alias in COL_ALIASES[field]:
            if len(alias) >= 3 and (alias in col or col in alias):
                return col
    return None


def _get(row, df: pd.DataFrame, field: str, default=0):
    col = _find_col(df, field)
    if col is None:
        return default
    val = row.get(col, default)
    return val if pd.notna(val) else default


def _safe_float(v, default: float = 0.0) -> float:
    try:
        f = float(v)
        return default if (f != f) else f
    except (TypeError, ValueError):
        return default


def _safe_str(v, default: str = "") -> str:
    s = str(v).strip() if v is not None else ""
    return default if s.lower() in ("nan", "none", "") else s


def _parse_file(content: bytes, filename: str) -> pd.DataFrame:
    if filename.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    else:
        df = pd.read_excel(io.BytesIO(content))
    df.columns = [
        str(c).strip().lower()
        .replace(" ", "_").replace("-", "_").replace(".", "_").replace("/", "_")
        for c in df.columns
    ]
    df = df.loc[:, df.columns != "nan"]
    id_col = _find_col(df, "emp_id")
    if id_col:
        def _is_employee_row(v) -> bool:
            if pd.isna(v):
                return False
            s = str(v).strip().lower()
            if s in ("", "nan", "total", "grand total", "totals"):
                return False
            try:
                n = float(s)
                return n > 0 and n == int(n)
            except ValueError:
                return len(s) <= 20
        df = df[df[id_col].apply(_is_employee_row)].reset_index(drop=True)
    return df


def _build_employees(df: pd.DataFrame) -> List[EmployeeInputLC]:
    employees = []
    for _, row in df.iterrows():
        basic   = _safe_float(_get(row, df, "basic", 0))
        da      = _safe_float(_get(row, df, "da", 0))
        hra     = _safe_float(_get(row, df, "hra", 0))
        special = _safe_float(_get(row, df, "special_allowance", 0))
        other   = _safe_float(_get(row, df, "other_allowances", 0))
        ctc     = _safe_float(_get(row, df, "ctc_monthly", 0))

        # Auto-split if only gross/CTC provided
        if basic == 0 and da == 0 and hra == 0 and special == 0 and other == 0:
            gross_col = next(
                (c for c in df.columns
                 if any(k in c for k in ("sal_rate", "salary_rate", "gross"))
                 and _safe_float(row.get(c, 0)) > 0),
                None,
            )
            if gross_col:
                g = _safe_float(row.get(gross_col, 0))
                if g > 0:
                    # Default split: 50% Basic (ensures CoW compliance), 25% HRA, 25% Other
                    basic   = round(g * 0.50)
                    hra     = round(g * 0.25)
                    other   = round(g * 0.25)

        if basic == 0 and da == 0 and hra == 0 and special == 0 and other == 0:
            continue

        days_in_month = int(_safe_float(_get(row, df, "days_in_month", 0)) or 30)
        days_worked   = int(_safe_float(_get(row, df, "days_worked", days_in_month)))
        days_worked   = min(days_worked, days_in_month)

        # Employment type — default to regular
        raw_type = _safe_str(_get(row, df, "employment_type", "regular"), "regular").lower()
        emp_type = "fixed_term" if "fix" in raw_type or "fte" in raw_type or "contract" in raw_type \
                   else "gig" if "gig" in raw_type or "platform" in raw_type or "freelan" in raw_type \
                   else "regular"

        years_svc  = _safe_float(_get(row, df, "years_of_service", 0))
        ot_hours   = _safe_float(_get(row, df, "ot_hours_month", 0))
        daily_hrs  = _safe_float(_get(row, df, "daily_avg_hours", 0)) or 8.0
        leave_bal  = _safe_float(_get(row, df, "leave_balance", 0))

        emp = EmployeeInputLC(
            emp_id=str(_get(row, df, "emp_id", "N/A")),
            name=str(_get(row, df, "name", "Unknown")),
            uan=str(_get(row, df, "uan", "")),
            pf_number=str(_get(row, df, "pf_number", "")),
            esic_number=str(_get(row, df, "esic_number", "")),
            basic=basic, da=da, hra=hra,
            special_allowance=special,
            other_allowances=other,
            ctc_monthly=ctc,
            days_in_month=days_in_month,
            days_worked=days_worked,
            employment_type=emp_type,
            years_of_service=years_svc,
            ot_hours_month=ot_hours,
            daily_avg_hours=daily_hrs,
            leave_balance_opening=leave_bal,
            advance_deduction=_safe_float(_get(row, df, "advance_deduction", 0)),
            bank_account=str(_get(row, df, "bank_account", "")),
            ifsc_code=str(_get(row, df, "ifsc_code", "")),
            designation=str(_get(row, df, "designation", "")),
            department=str(_get(row, df, "department", "")),
        )
        employees.append(emp)
    return employees


def _get_session(session_id: str) -> dict:
    if session_id not in SESSIONS:
        raise HTTPException(404, "Session expired — please re-upload your file.")
    return SESSIONS[session_id]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/process", response_class=HTMLResponse)
async def process_payroll(
    request: Request,
    file: UploadFile = File(...),
    company_name: str = Form("New Labour Codes Payroll Demo"),
    establishment_id: str = Form("MH/MUM/12345"),
    month: int = Form(...),
    year: int = Form(...),
):
    try:
        content  = await file.read()
        df       = _parse_file(content, file.filename)
        employees = _build_employees(df)
        results  = [calculate_payroll_lc(emp, month, year) for emp in employees]

        ecr_text  = generate_ecr_lc(results, establishment_id, company_name, month, year)
        esic_text = generate_esic_csv_lc(results, month, year)
        summary   = build_summary_lc(results)

        session_id = str(uuid.uuid4())
        SESSIONS[session_id] = {
            "results":          results,
            "ecr_text":         ecr_text,
            "esic_text":        esic_text,
            "company_name":     company_name,
            "establishment_id": establishment_id,
            "month":            month,
            "year":             year,
            "summary":          summary,
        }

        return templates.TemplateResponse("results.html", {
            "request":      request,
            "session_id":   session_id,
            "results":      results,
            "summary":      summary,
            "company_name": company_name,
            "month":        month,
            "year":         year,
            "month_name":   MONTH_NAMES[month],
        })

    except Exception as exc:
        import traceback
        return HTMLResponse(f"""
        <div style="font-family:sans-serif;padding:2rem;max-width:700px;margin:auto">
          <h2 style="color:#b91c1c">Processing Error</h2>
          <p><b>{exc}</b></p>
          <pre style="background:#f3f4f6;padding:1rem;border-radius:8px;font-size:.8rem;overflow-x:auto">{traceback.format_exc()}</pre>
          <p><a href="/">\u2190 Try again</a></p>
        </div>""", status_code=400)


@app.get("/compliance/{session_id}", response_class=HTMLResponse)
async def compliance_report(request: Request, session_id: str):
    s = _get_session(session_id)
    return templates.TemplateResponse("compliance.html", {
        "request":      request,
        "session_id":   session_id,
        "results":      s["results"],
        "summary":      s["summary"],
        "company_name": s["company_name"],
        "month":        s["month"],
        "year":         s["year"],
        "month_name":   MONTH_NAMES[s["month"]],
        "today":        date.today().strftime("%d %B %Y"),
    })


@app.get("/download/slip/{session_id}/{emp_id}")
async def download_slip(session_id: str, emp_id: str):
    s = _get_session(session_id)
    result = next((r for r in s["results"] if r.emp_id == emp_id), None)
    if not result:
        raise HTTPException(404, "Employee not found")
    pdf = generate_salary_slip_lc_pdf(result, s["month"], s["year"], s["company_name"])
    fname = f"SalarySlip_LC_{emp_id}_{s['year']}_{s['month']:02d}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/download/all-slips/{session_id}")
async def download_all_slips(session_id: str):
    s = _get_session(session_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in s["results"]:
            pdf  = generate_salary_slip_lc_pdf(r, s["month"], s["year"], s["company_name"])
            name = f"SalarySlip_LC_{r.emp_id}_{r.name.replace(' ','_')}_{s['year']}_{s['month']:02d}.pdf"
            zf.writestr(name, pdf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="SalarySlips_LC_{s["year"]}_{s["month"]:02d}.zip"'},
    )


@app.get("/download/ecr/{session_id}")
async def download_ecr(session_id: str):
    s = _get_session(session_id)
    return StreamingResponse(
        io.BytesIO(s["ecr_text"].encode()),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="ECR_LC_{s["year"]}_{s["month"]:02d}.txt"'},
    )


@app.get("/download/esic/{session_id}")
async def download_esic(session_id: str):
    s = _get_session(session_id)
    return StreamingResponse(
        io.BytesIO(s["esic_text"].encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="ESIC_LC_{s["year"]}_{s["month"]:02d}.csv"'},
    )


@app.get("/download/bank-file/{session_id}")
async def download_bank_file(session_id: str):
    s = _get_session(session_id)
    rows = ["SL_NO,ACCOUNT_NAME,ACCOUNT_NUMBER,IFSC_CODE,NET_AMOUNT,PAYMENT_REF,REMARKS"]
    for i, r in enumerate(s["results"], 1):
        ref = f"SAL-LC/{s['year']}/{s['month']:02d}/{r.emp_id}"
        rows.append(
            f"{i},{r.name},{r.bank_account or 'N/A'},{r.ifsc_code or 'N/A'},"
            f"{int(r.net_pay)},{ref},Salary {MONTH_NAMES[s['month']]} {s['year']}"
        )
    return StreamingResponse(
        io.BytesIO("\n".join(rows).encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="BankFile_LC_{s["year"]}_{s["month"]:02d}.csv"'},
    )


@app.get("/download/payroll-register/{session_id}")
async def download_payroll_register(session_id: str):
    s = _get_session(session_id)
    rows = [
        "EMP_ID,NAME,EMP_TYPE,DAYS_IN_MONTH,DAYS_WORKED,NCP_DAYS,"
        "BASIC,DA,HRA,SPECIAL,OTHER,GROSS,"
        "CORE_WAGES,CTC_GROSS,WAGE_RATIO_PCT,WAGE_COMPLIANT,ADJUSTED_WAGES,"
        "PF_WAGES,EMP_PF,ER_EPF,ER_EPS,PF_BASE_ADJUSTED,"
        "EMP_ESIC,ER_ESIC,PT,LWF_EMP,LWF_ER,"
        "OT_HOURS,OT_PAY,OT_COMPLIANT,"
        "GRATUITY_ELIGIBLE,MONTHLY_GRATUITY_ACCRUAL,GRATUITY_TOTAL_ACCRUED,"
        "LEAVE_EARNED,LEAVE_CF_BALANCE,"
        "ADVANCE,TOTAL_DEDUCTIONS,NET_PAY,"
        "COMPLIANCE_FLAGS"
    ]
    for r in s["results"]:
        flag_codes = "|".join(f.code for f in r.flags) or "NONE"
        rows.append(
            f"{r.emp_id},{r.name},{r.employment_type},"
            f"{r.days_in_month},{r.days_worked},{r.ncp_days},"
            f"{int(r.earned_basic)},{int(r.earned_da)},{int(r.earned_hra)},"
            f"{int(r.earned_special)},{int(r.earned_other)},{int(r.gross_earned)},"
            f"{int(r.core_wages_earned)},{int(r.ctc_gross_monthly)},"
            f"{r.wage_ratio_actual*100:.1f},{r.wage_ratio_compliant},{int(r.adjusted_wages)},"
            f"{int(r.pf_wages)},{int(r.employee_pf)},{int(r.employer_epf)},{int(r.employer_eps)},"
            f"{r.pf_base_adjusted},"
            f"{int(r.employee_esic)},{int(r.employer_esic)},{int(r.professional_tax)},"
            f"{int(r.lwf_employee)},{int(r.lwf_employer)},"
            f"{r.ot_hours_month:.1f},{int(r.ot_pay)},{r.ot_compliant},"
            f"{r.gratuity_eligible},{int(r.monthly_gratuity_accrual)},{int(r.gratuity_total_accrued)},"
            f"{r.leave_earned_this_month:.2f},{r.leave_carry_forward_net:.1f},"
            f"{int(r.advance_deduction)},{int(r.total_deductions)},{int(r.net_pay)},"
            f"{flag_codes}"
        )
    return StreamingResponse(
        io.BytesIO("\n".join(rows).encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="PayrollRegister_LC_{s["year"]}_{s["month"]:02d}.csv"'},
    )


@app.get("/download/compliance-report/{session_id}")
async def download_compliance_csv(session_id: str):
    """Download full compliance flag report as CSV."""
    s = _get_session(session_id)
    rows = ["EMP_ID,NAME,EMP_TYPE,SEVERITY,FLAG_CODE,DESCRIPTION,DETAIL"]
    for r in s["results"]:
        if not r.flags:
            rows.append(f'{r.emp_id},{r.name},{r.employment_type},OK,COMPLIANT,"No issues","All checks passed"')
        for f in r.flags:
            detail = f.detail.replace(",", ";")
            desc   = f.description.replace(",", ";")
            rows.append(
                f'{r.emp_id},{r.name},{r.employment_type},'
                f'{f.severity.upper()},{f.code},"{desc}","{detail}"'
            )
    return StreamingResponse(
        io.BytesIO("\n".join(rows).encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="ComplianceReport_LC_{s["year"]}_{s["month"]:02d}.csv"'},
    )


@app.get("/sample-csv")
async def download_sample_csv():
    with open("sample_lc_data.csv", "rb") as f:
        content = f.read()
    return StreamingResponse(
        io.BytesIO(content), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sample_lc_payroll.csv"'},
    )
