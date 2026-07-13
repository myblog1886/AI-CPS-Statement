"""
FastAPI Payroll Demo — CPS LLP India Compliance Copilot
Run: python3 -m uvicorn main:app --reload
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

from ecr_generator import generate_ecr, generate_esic_csv
from ecr_pdf_generator import generate_ecr_validation_pdf
from payroll_engine import (
    EmployeeInput, PayrollResult, MONTH_NAMES,
    calculate_payroll, audit_variance,
)
from pdf_generator import generate_salary_slip_pdf

app = FastAPI(title="CPS LLP — India Payroll Copilot")
templates = Jinja2Templates(directory="templates")

SESSIONS: Dict[str, dict] = {}


# ── Column aliases — broad coverage of real-world file variations ─────────────
COL_ALIASES = {
    "emp_id":            ["emp_id", "employee_id", "empid", "id", "sr_no", "sr_no_",
                          "sl_no", "serial_no", "emp_code", "employee_code",
                          "staff_id", "payroll_id", "sno", "s_no"],
    "name":              ["name", "employee_name", "emp_name", "full_name",
                          "employee", "staff_name", "worker_name"],
    "uan":               ["uan", "uan_number", "uan_no", "universal_account_number"],
    "pf_number":         ["pf_number", "pf_no", "pf_account", "pfnumber",
                          "epf_number", "pf_account_no", "epf_no", "pf_no_"],
    "esic_number":       ["esic_number", "esic_no", "ip_number", "esicnumber",
                          "esic_ip", "ip_no"],
    "basic":             ["basic", "basic_salary", "basic_pay", "basic_wages",
                          "basic_ctc", "base_salary", "bs"],
    "da":                ["da", "dearness_allowance", "dearness_allow",
                          "da_amount", "dearness"],
    "hra":               ["hra", "house_rent_allowance", "house_rent",
                          "hra_amount", "housing_allowance"],
    "other_allowances":  ["other_allowances", "other", "special_allowance",
                          "other_allow", "conveyance", "medical_allowance",
                          "transport_allowance", "misc_allowance", "other_pay",
                          "special_pay", "fixed_allowance", "flex_allowance",
                          "supplementary_allowance", "ot_rs_", "ot_rs", "ot_amount",
                          "overtime_amount", "overtime"],
    "days_in_month":     ["days_in_month", "total_days", "working_days_in_month",
                          "calendar_days", "month_days", "payable_days_in_month",
                          "month", "month_"],
    "days_worked":       ["days_worked", "days_present", "present_days",
                          "actual_days", "paid_days", "working_days",
                          "attendance_days", "days_paid", "final_days"],
    "advance_deduction": ["advance_deduction", "advance", "loan_deduction",
                          "loan", "recovery", "loan_recovery", "advance_recovery"],
    "bank_account":      ["bank_account", "account_number", "bank_acc",
                          "acc_no", "account_no", "bank_account_number",
                          "salary_account", "bank_acct"],
    "ifsc_code":         ["ifsc_code", "ifsc", "bank_ifsc", "ifsc_no",
                          "bank_code", "ifsc_number"],
    "designation":       ["designation", "role", "position", "job_title",
                          "title", "grade"],
    "department":        ["department", "dept", "division", "section",
                          "cost_centre", "team"],
}

# Columns whose headers indicate a totals/summary row — used to strip them
_TOTALS_SENTINEL_COLS = {"total", "grand_total", "totals"}


def _find_col(df: pd.DataFrame, field: str) -> Optional[str]:
    cols = df.columns.tolist()
    # 1. Exact match
    for alias in COL_ALIASES[field]:
        if alias in cols:
            return alias
    # 2. Substring match (alias is contained in col name, or vice-versa)
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
    """Convert value to float, returning default for NaN/None/empty."""
    try:
        f = float(v)
        return default if (f != f) else f   # NaN check: NaN != NaN
    except (TypeError, ValueError):
        return default


def _parse_file(content: bytes, filename: str) -> pd.DataFrame:
    if filename.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    else:
        df = pd.read_excel(io.BytesIO(content))

    # ── Normalise column names ────────────────────────────────────────────────
    df.columns = [
        str(c).strip().lower()
        .replace(" ", "_").replace("-", "_").replace(".", "_").replace("/", "_")
        for c in df.columns
    ]

    # ── Drop columns whose header normalised to "nan" (blank separator cols) ─
    df = df.loc[:, df.columns != "nan"]

    # ── Drop rows that are clearly totals/footers, not employees ─────────────
    # Strategy: keep only rows where the emp_id/sr_no cell is a positive integer
    # or a short alphanumeric string (e.g. "E001"). Blank rows and totals rows
    # typically have NaN or text like "Total", "Grand Total" in that position.
    id_col = _find_col(df, "emp_id")
    if id_col:
        def _is_employee_row(v) -> bool:
            if pd.isna(v):
                return False
            s = str(v).strip().lower()
            if s in ("", "nan", "total", "grand total", "totals", "sub total"):
                return False
            # Accept numeric IDs or alphanumeric codes like E001
            try:
                n = float(s)
                return n > 0 and n == int(n)   # positive integer
            except ValueError:
                return len(s) <= 20             # short alphanumeric string
        df = df[df[id_col].apply(_is_employee_row)].reset_index(drop=True)

    return df


def _build_employees(df: pd.DataFrame) -> List[EmployeeInput]:
    employees = []
    for _, row in df.iterrows():
        basic = _safe_float(_get(row, df, "basic", 0))
        da    = _safe_float(_get(row, df, "da",    0))
        hra   = _safe_float(_get(row, df, "hra",   0))
        other = _safe_float(_get(row, df, "other_allowances", 0))

        # ── Gross-only files: split into components ───────────────────────────
        if basic == 0 and da == 0 and hra == 0 and other == 0:
            # Prefer "sal_rate" / "salary_rate" / "ctc" columns as gross proxy
            gross_col = next(
                (c for c in df.columns
                 if any(k in c for k in ("sal_rate", "salary_rate", "ctc", "gross"))
                 and _safe_float(row.get(c, 0)) > 0),
                None,
            )
            if gross_col:
                g = _safe_float(row.get(gross_col, 0))
                if g > 0:
                    basic = round(g * 0.50)
                    hra   = round(g * 0.30)
                    other = round(g * 0.20)

        # ── Skip rows where we still have no salary data ──────────────────────
        if basic == 0 and da == 0 and hra == 0 and other == 0:
            continue

        days_in_month = int(_safe_float(_get(row, df, "days_in_month", 0)) or 30)
        days_worked   = int(_safe_float(_get(row, df, "days_worked", days_in_month)))
        # Guard: days_worked cannot exceed days_in_month
        days_worked = min(days_worked, days_in_month)

        emp = EmployeeInput(
            emp_id=str(_get(row, df, "emp_id", "N/A")),
            name=str(_get(row, df, "name", "Unknown")),
            uan=str(_get(row, df, "uan", "")),
            pf_number=str(_get(row, df, "pf_number", "")),
            esic_number=str(_get(row, df, "esic_number", "")),
            basic=basic,
            da=da,
            hra=hra,
            other_allowances=other,
            days_in_month=days_in_month,
            days_worked=days_worked,
            advance_deduction=_safe_float(_get(row, df, "advance_deduction", 0)),
            bank_account=str(_get(row, df, "bank_account", "")),
            ifsc_code=str(_get(row, df, "ifsc_code", "")),
            designation=str(_get(row, df, "designation", "")),
            department=str(_get(row, df, "department", "")),
        )
        employees.append(emp)
    return employees


def _build_summary(results: List[PayrollResult]) -> dict:
    return {
        "total_employees":     len(results),
        "esic_count":          sum(1 for r in results if r.esic_applicable),
        "total_gross":         sum(r.gross_earned      for r in results),
        "total_net":           sum(r.net_pay           for r in results),
        "total_employee_pf":   sum(r.employee_pf       for r in results),
        "total_employer_epf":  sum(r.employer_epf      for r in results),
        "total_employer_eps":  sum(r.employer_eps      for r in results),
        "total_employer_pf":   sum(r.employer_epf + r.employer_eps for r in results),
        "total_pf_challan":    sum(r.employee_pf + r.employer_epf + r.employer_eps for r in results),
        "total_employee_esic": sum(r.employee_esic     for r in results),
        "total_employer_esic": sum(r.employer_esic     for r in results),
        "total_esic_challan":  sum(r.employee_esic + r.employer_esic for r in results),
        "total_pt":            sum(r.professional_tax  for r in results),
        "total_lwf_employee":  sum(r.lwf_employee      for r in results),
        "total_lwf_employer":  sum(r.lwf_employer      for r in results),
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/process", response_class=HTMLResponse)
async def process_payroll(
    request: Request,
    file: UploadFile = File(...),
    company_name: str = Form("Corporate Personnel Services LLP"),
    establishment_id: str = Form("MH/MUM/12345"),
    month: int = Form(...),
    year: int = Form(...),
):
    try:
        content = await file.read()
        df = _parse_file(content, file.filename)
        employees = _build_employees(df)
        results = [calculate_payroll(emp, month, year) for emp in employees]

        ecr_text  = generate_ecr(results, establishment_id, company_name, month, year)
        esic_text = generate_esic_csv(results, month, year)
        summary   = _build_summary(results)

        session_id = str(uuid.uuid4())
        SESSIONS[session_id] = {
            "results":          results,
            "employees":        employees,
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
        err_html = f"""
        <div style="font-family:sans-serif;padding:2rem;max-width:700px;margin:auto">
          <h2 style="color:#b91c1c">Processing Error</h2>
          <p><b>{exc}</b></p>
          <pre style="background:#f3f4f6;padding:1rem;border-radius:8px;font-size:.8rem;overflow-x:auto">{traceback.format_exc()}</pre>
          <p><a href="/">← Try again</a></p>
        </div>"""
        return HTMLResponse(err_html, status_code=400)


@app.post("/audit", response_class=HTMLResponse)
async def audit_payroll(
    request: Request,
    prev_file: UploadFile = File(...),
    curr_file: UploadFile = File(...),
    company_name: str = Form("Corporate Personnel Services LLP"),
    prev_month: int = Form(...),
    prev_year: int = Form(...),
    curr_month: int = Form(...),
    curr_year: int = Form(...),
):
    try:
        prev_df = _parse_file(await prev_file.read(), prev_file.filename)
        curr_df = _parse_file(await curr_file.read(), curr_file.filename)

        prev_emps = _build_employees(prev_df)
        curr_emps = _build_employees(curr_df)

        prev_results = [calculate_payroll(e, prev_month, prev_year) for e in prev_emps]
        curr_results = [calculate_payroll(e, curr_month, curr_year) for e in curr_emps]

        flags = audit_variance(prev_results, curr_results)

        prev_summary = _build_summary(prev_results)
        curr_summary = _build_summary(curr_results)

        session_id = str(uuid.uuid4())
        SESSIONS[session_id] = {
            "results":      curr_results,
            "ecr_text":     generate_ecr(curr_results, "MH/MUM/12345", company_name, curr_month, curr_year),
            "esic_text":    generate_esic_csv(curr_results, curr_month, curr_year),
            "company_name": company_name,
            "establishment_id": "MH/MUM/12345",
            "month":        curr_month,
            "year":         curr_year,
            "summary":      curr_summary,
        }

        return templates.TemplateResponse("audit.html", {
            "request":      request,
            "flags":        flags,
            "company_name": company_name,
            "prev_month":   MONTH_NAMES[prev_month],
            "curr_month":   MONTH_NAMES[curr_month],
            "prev_year":    prev_year,
            "curr_year":    curr_year,
            "prev_summary": prev_summary,
            "curr_summary": curr_summary,
            "session_id":   session_id,
        })

    except Exception as exc:
        import traceback
        err_html = f"""
        <div style="font-family:sans-serif;padding:2rem;max-width:700px;margin:auto">
          <h2 style="color:#b91c1c">Audit Error</h2>
          <p><b>{exc}</b></p>
          <pre style="background:#f3f4f6;padding:1rem;border-radius:8px;font-size:.8rem">{traceback.format_exc()}</pre>
          <p><a href="/">← Try again</a></p>
        </div>"""
        return HTMLResponse(err_html, status_code=400)


@app.get("/challan-confirmation/{session_id}", response_class=HTMLResponse)
async def challan_confirmation(request: Request, session_id: str):
    s = _get_session(session_id)
    return templates.TemplateResponse("challan_confirmation.html", {
        "request":          request,
        "session_id":       session_id,
        "company_name":     s["company_name"],
        "establishment_id": s["establishment_id"],
        "month":            s["month"],
        "year":             s["year"],
        "month_name":       MONTH_NAMES[s["month"]],
        "summary":          s["summary"],
        "results":          s["results"],
        "today":            date.today().strftime("%d %B %Y"),
    })


@app.get("/download/ecr-validation-pdf/{session_id}")
async def download_ecr_validation_pdf(session_id: str):
    from datetime import datetime
    s = _get_session(session_id)
    pdf = generate_ecr_validation_pdf(
        results=s["results"],
        establishment_id=s["establishment_id"],
        establishment_name=s["company_name"],
        month=s["month"],
        year=s["year"],
        upload_datetime=datetime.now(),
    )
    fname = f"ECR_Validation_Acknowledgement_{s['year']}_{s['month']:02d}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/download/ecr/{session_id}")
async def download_ecr(session_id: str):
    s = _get_session(session_id)
    fname = f"ECR_{s['year']}_{s['month']:02d}.txt"
    return StreamingResponse(
        io.BytesIO(s["ecr_text"].encode()),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/download/esic/{session_id}")
async def download_esic(session_id: str):
    s = _get_session(session_id)
    fname = f"ESIC_Contribution_{s['year']}_{s['month']:02d}.csv"
    return StreamingResponse(
        io.BytesIO(s["esic_text"].encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/download/bank-file/{session_id}")
async def download_bank_file(session_id: str):
    s = _get_session(session_id)
    rows = ["SL_NO,ACCOUNT_NAME,ACCOUNT_NUMBER,IFSC_CODE,NET_AMOUNT,PAYMENT_REF,REMARKS"]
    for i, r in enumerate(s["results"], 1):
        ref = f"SAL/{s['year']}/{s['month']:02d}/{r.emp_id}"
        rows.append(
            f"{i},{r.name},{r.bank_account or 'N/A'},{r.ifsc_code or 'N/A'},"
            f"{int(r.net_pay)},{ref},Salary {MONTH_NAMES[s['month']]} {s['year']}"
        )
    fname = f"BankPaymentAdvice_{s['year']}_{s['month']:02d}.csv"
    return StreamingResponse(
        io.BytesIO("\n".join(rows).encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/download/payroll-register/{session_id}")
async def download_payroll_register(session_id: str):
    s = _get_session(session_id)
    rows = [
        "EMP_ID,NAME,DAYS_IN_MONTH,DAYS_WORKED,NCP_DAYS,"
        "BASIC,DA,HRA,OTHER,GROSS,"
        "PF_WAGES,EMP_PF,ER_EPF,ER_EPS,"
        "EMP_ESIC,ER_ESIC,PT,LWF_EMP,LWF_ER,"
        "ADVANCE,TOTAL_DEDUCTIONS,NET_PAY"
    ]
    for r in s["results"]:
        rows.append(
            f"{r.emp_id},{r.name},{r.days_in_month},{r.days_worked},{r.ncp_days},"
            f"{int(r.earned_basic)},{int(r.earned_da)},{int(r.earned_hra)},{int(r.earned_other)},{int(r.gross_earned)},"
            f"{int(r.pf_wages)},{int(r.employee_pf)},{int(r.employer_epf)},{int(r.employer_eps)},"
            f"{int(r.employee_esic)},{int(r.employer_esic)},{int(r.professional_tax)},{int(r.lwf_employee)},{int(r.lwf_employer)},"
            f"{int(r.advance_deduction)},{int(r.total_deductions)},{int(r.net_pay)}"
        )
    fname = f"PayrollRegister_{s['year']}_{s['month']:02d}.csv"
    return StreamingResponse(
        io.BytesIO("\n".join(rows).encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/download/slip/{session_id}/{emp_id}")
async def download_slip(session_id: str, emp_id: str):
    s = _get_session(session_id)
    result = next((r for r in s["results"] if r.emp_id == emp_id), None)
    if not result:
        raise HTTPException(404, "Employee not found")
    pdf = generate_salary_slip_pdf(result, s["month"], s["year"], s["company_name"])
    fname = f"SalarySlip_{emp_id}_{s['year']}_{s['month']:02d}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/download/all-slips/{session_id}")
async def download_all_slips(session_id: str):
    s = _get_session(session_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in s["results"]:
            pdf = generate_salary_slip_pdf(r, s["month"], s["year"], s["company_name"])
            fname = f"SalarySlip_{r.emp_id}_{r.name.replace(' ','_')}_{s['year']}_{s['month']:02d}.pdf"
            zf.writestr(fname, pdf)
    buf.seek(0)
    fname = f"SalarySlips_{s['year']}_{s['month']:02d}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/disburse/{session_id}", response_class=HTMLResponse)
async def disburse_page(request: Request, session_id: str):
    s = _get_session(session_id)
    return templates.TemplateResponse("disburse.html", {
        "request":      request,
        "session_id":   session_id,
        "results":      s["results"],
        "summary":      s["summary"],
        "company_name": s["company_name"],
        "month":        s["month"],
        "year":         s["year"],
        "month_name":   MONTH_NAMES[s["month"]],
    })


@app.get("/disburse/status/{session_id}")
async def disburse_status(session_id: str):
    """
    Server-Sent Events stream — simulates real-time per-employee bank transfers.
    In production this would call your bank API (RazorpayX, Cashfree Payouts,
    YES Bank CMS, HDFC SmartPay, etc.) and stream actual statuses.
    """
    import asyncio, json, random
    s = _get_session(session_id)
    results = s["results"]

    async def event_stream():
        yield "retry: 1000\n\n"
        total_sent = 0
        for i, r in enumerate(results):
            await asyncio.sleep(0.9 + random.uniform(0, 0.4))
            # Simulate occasional bank-side delays for realism
            status = "SUCCESS"
            utr = f"UTR{year_tag}{random.randint(10**11, 10**12 - 1)}"
            if not r.bank_account or r.bank_account in ("", "nan", "None"):
                status = "FAILED"
                utr = "—"
            total_sent += r.net_pay if status == "SUCCESS" else 0
            payload = json.dumps({
                "index":       i,
                "emp_id":      r.emp_id,
                "name":        r.name,
                "bank":        r.bank_account or "N/A",
                "ifsc":        r.ifsc_code    or "N/A",
                "amount":      int(r.net_pay),
                "status":      status,
                "utr":         utr,
                "total_sent":  int(total_sent),
                "done":        i == len(results) - 1,
            })
            yield f"data: {payload}\n\n"

    year_tag = str(s["year"])[2:]
    from fastapi.responses import StreamingResponse as SR
    return SR(event_stream(), media_type="text/event-stream",
              headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/sample-csv")
async def download_sample_csv():
    with open("sample_data.csv", "rb") as f:
        content = f.read()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sample_payroll_december_2025.csv"'},
    )


@app.get("/sample-csv-prev")
async def download_sample_csv_prev():
    with open("sample_data_november.csv", "rb") as f:
        content = f.read()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sample_payroll_november_2025.csv"'},
    )


def _get_session(session_id: str) -> dict:
    if session_id not in SESSIONS:
        raise HTTPException(404, "Session expired — please re-upload your file.")
    return SESSIONS[session_id]
