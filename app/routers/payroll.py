import io, uuid, zipfile
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.payroll_engine import EmployeeInput, PayrollResult, MONTH_NAMES, calculate_payroll, audit_variance
from app.ecr_generator import generate_ecr, generate_esic_csv
from app.ecr_pdf_generator import generate_ecr_validation_pdf
from app.pdf_generator import generate_salary_slip_pdf
from app.db import save_run

router = APIRouter()
templates = Jinja2Templates(directory="templates")

SESSIONS: dict = {}

COL_ALIASES = {
    "emp_id":            ["emp_id","employee_id","empid","id","sr_no","sl_no","emp_code","employee_code","sno"],
    "name":              ["name","employee_name","emp_name","full_name","employee","staff_name"],
    "uan":               ["uan","uan_number","uan_no"],
    "pf_number":         ["pf_number","pf_no","pf_account","epf_number","pf_no_"],
    "esic_number":       ["esic_number","esic_no","ip_number","esic_ip"],
    "basic":             ["basic","basic_salary","basic_pay","basic_wages","basic_ctc","base_salary","bs"],
    "da":                ["da","dearness_allowance","dearness_allow","da_amount"],
    "hra":               ["hra","house_rent_allowance","house_rent","hra_amount"],
    "other_allowances":  ["other_allowances","other","special_allowance","other_allow","conveyance","ot_rs","ot_amount","overtime_amount"],
    "days_in_month":     ["days_in_month","total_days","working_days_in_month","calendar_days","month_days"],
    "days_worked":       ["days_worked","days_present","present_days","actual_days","paid_days","working_days"],
    "advance_deduction": ["advance_deduction","advance","loan_deduction","loan","recovery"],
    "bank_account":      ["bank_account","account_number","bank_acc","acc_no","account_no"],
    "ifsc_code":         ["ifsc_code","ifsc","bank_ifsc","bank_code"],
    "designation":       ["designation","role","position","job_title","title","grade"],
    "department":        ["department","dept","division","section","cost_centre","team"],
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


def _get(row, df, field, default=0):
    col = _find_col(df, field)
    if col is None:
        return default
    val = row.get(col, default)
    return val if pd.notna(val) else default


def _safe_float(v, default=0.0):
    try:
        f = float(v)
        return default if f != f else f
    except (TypeError, ValueError):
        return default


def parse_file(content: bytes, filename: str) -> pd.DataFrame:
    if filename.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    else:
        df = pd.read_excel(io.BytesIO(content))
    df.columns = [
        str(c).strip().lower().replace(" ","_").replace("-","_").replace(".","_").replace("/","_")
        for c in df.columns
    ]
    df = df.loc[:, df.columns != "nan"]
    id_col = _find_col(df, "emp_id")
    if id_col:
        def _is_emp(v):
            if pd.isna(v): return False
            s = str(v).strip().lower()
            if s in ("","nan","total","grand total","totals","sub total"): return False
            try:
                n = float(s)
                return n > 0 and n == int(n)
            except ValueError:
                return len(s) <= 20
        df = df[df[id_col].apply(_is_emp)].reset_index(drop=True)
    return df


def build_employees(df: pd.DataFrame) -> List[EmployeeInput]:
    employees = []
    for _, row in df.iterrows():
        basic = _safe_float(_get(row, df, "basic", 0))
        da    = _safe_float(_get(row, df, "da", 0))
        hra   = _safe_float(_get(row, df, "hra", 0))
        other = _safe_float(_get(row, df, "other_allowances", 0))
        if basic == da == hra == other == 0:
            gross_col = next(
                (c for c in df.columns if any(k in c for k in ("sal_rate","salary_rate","ctc","gross"))
                 and _safe_float(row.get(c, 0)) > 0), None)
            if gross_col:
                g = _safe_float(row.get(gross_col, 0))
                if g > 0:
                    basic, hra, other = round(g*.50), round(g*.30), round(g*.20)
        if basic == da == hra == other == 0:
            continue
        dim = int(_safe_float(_get(row, df, "days_in_month", 0)) or 30)
        dw  = min(int(_safe_float(_get(row, df, "days_worked", dim))), dim)
        employees.append(EmployeeInput(
            emp_id=str(_get(row, df, "emp_id", "N/A")),
            name=str(_get(row, df, "name", "Unknown")),
            uan=str(_get(row, df, "uan", "")),
            pf_number=str(_get(row, df, "pf_number", "")),
            esic_number=str(_get(row, df, "esic_number", "")),
            basic=basic, da=da, hra=hra, other_allowances=other,
            days_in_month=dim, days_worked=dw,
            advance_deduction=_safe_float(_get(row, df, "advance_deduction", 0)),
            bank_account=str(_get(row, df, "bank_account", "")),
            ifsc_code=str(_get(row, df, "ifsc_code", "")),
            designation=str(_get(row, df, "designation", "")),
            department=str(_get(row, df, "department", "")),
        ))
    return employees


def build_summary(results: List[PayrollResult]) -> dict:
    return {
        "total_employees":     len(results),
        "esic_count":          sum(1 for r in results if r.esic_applicable),
        "total_gross":         sum(r.gross_earned for r in results),
        "total_net":           sum(r.net_pay for r in results),
        "total_employee_pf":   sum(r.employee_pf for r in results),
        "total_employer_epf":  sum(r.employer_epf for r in results),
        "total_employer_eps":  sum(r.employer_eps for r in results),
        "total_employer_pf":   sum(r.employer_epf + r.employer_eps for r in results),
        "total_pf_challan":    sum(r.employee_pf + r.employer_epf + r.employer_eps for r in results),
        "total_employee_esic": sum(r.employee_esic for r in results),
        "total_employer_esic": sum(r.employer_esic for r in results),
        "total_esic_challan":  sum(r.employee_esic + r.employer_esic for r in results),
        "total_pt":            sum(r.professional_tax for r in results),
        "total_lwf_employee":  sum(r.lwf_employee for r in results),
        "total_lwf_employer":  sum(r.lwf_employer for r in results),
    }


def _error_html(message: str, back_url: str, detail: str = "") -> str:
    detail_block = f'<pre style="background:#f3f4f6;padding:1rem;border-radius:8px;font-size:.8rem;overflow-x:auto">{detail}</pre>' if detail else ""
    return f"""
    <div style="font-family:sans-serif;padding:2rem;max-width:700px;margin:auto">
      <h2 style="color:#b91c1c">&#9888; Processing Error</h2>
      <p style="font-size:1.1rem"><b>{message}</b></p>
      {detail_block}
      <p><a href="{back_url}" style="color:#2563eb">&#8592; Go back</a></p>
    </div>"""


@router.post("/process", response_class=HTMLResponse)
async def process_payroll(
    request: Request,
    file: UploadFile = File(...),
    company_name: str = Form("Corporate Personnel Services LLP"),
    establishment_id: str = Form("MH/MUM/12345"),
    month: int = Form(...),
    year: int = Form(...),
):
    allowed = (".csv", ".xlsx", ".xls")
    if not any(file.filename.lower().endswith(ext) for ext in allowed):
        return HTMLResponse(_error_html("Invalid file type. Please upload a .csv or .xlsx file.", "/"), 400)

    try:
        content = await file.read()
        if len(content) == 0:
            return HTMLResponse(_error_html("Uploaded file is empty.", "/"), 400)

        df = parse_file(content, file.filename)
        if df.empty:
            return HTMLResponse(_error_html("No valid employee rows found. Check that column headers are present.", "/"), 400)

        employees = build_employees(df)
        if not employees:
            return HTMLResponse(_error_html(f"Parsed {len(df)} rows but could not extract salary data. Ensure columns like 'basic', 'hra', or 'gross' are present.", "/"), 400)

        results = [calculate_payroll(emp, month, year) for emp in employees]
        ecr_text  = generate_ecr(results, establishment_id, company_name, month, year)
        esic_text = generate_esic_csv(results, month, year)
        summary   = build_summary(results)

        run_id = str(uuid.uuid4())
        try:
            run_id = save_run(company_name, establishment_id, month, year, summary, results, ecr_text, esic_text)
        except Exception:
            pass

        SESSIONS[run_id] = {
            "results": results, "employees": employees,
            "ecr_text": ecr_text, "esic_text": esic_text,
            "company_name": company_name, "establishment_id": establishment_id,
            "month": month, "year": year, "summary": summary,
        }

        return templates.TemplateResponse("results.html", {
            "request": request, "session_id": run_id,
            "results": results, "summary": summary,
            "company_name": company_name, "month": month, "year": year,
            "month_name": MONTH_NAMES[month],
        })

    except Exception as exc:
        import traceback
        return HTMLResponse(_error_html(str(exc), "/", traceback.format_exc()), 400)


def _get_session(session_id: str) -> dict:
    if session_id not in SESSIONS:
        raise HTTPException(404, "Session expired — please re-upload your file.")
    return SESSIONS[session_id]


@router.get("/download/ecr/{session_id}")
async def download_ecr(session_id: str):
    s = _get_session(session_id)
    fname = f"ECR_{s['year']}_{s['month']:02d}.txt"
    return StreamingResponse(io.BytesIO(s["ecr_text"].encode()), media_type="text/plain",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/download/esic/{session_id}")
async def download_esic(session_id: str):
    s = _get_session(session_id)
    fname = f"ESIC_{s['year']}_{s['month']:02d}.csv"
    return StreamingResponse(io.BytesIO(s["esic_text"].encode()), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/download/bank-file/{session_id}")
async def download_bank_file(session_id: str):
    s = _get_session(session_id)
    rows = ["SL_NO,ACCOUNT_NAME,ACCOUNT_NUMBER,IFSC_CODE,NET_AMOUNT,PAYMENT_REF,REMARKS"]
    for i, r in enumerate(s["results"], 1):
        ref = f"SAL/{s['year']}/{s['month']:02d}/{r.emp_id}"
        rows.append(f"{i},{r.name},{r.bank_account or 'N/A'},{r.ifsc_code or 'N/A'},{int(r.net_pay)},{ref},Salary {MONTH_NAMES[s['month']]} {s['year']}")
    fname = f"BankAdvice_{s['year']}_{s['month']:02d}.csv"
    return StreamingResponse(io.BytesIO("\n".join(rows).encode()), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/download/payroll-register/{session_id}")
async def download_payroll_register(session_id: str):
    s = _get_session(session_id)
    rows = ["EMP_ID,NAME,DAYS_IN_MONTH,DAYS_WORKED,NCP_DAYS,BASIC,DA,HRA,OTHER,GROSS,PF_WAGES,EMP_PF,ER_EPF,ER_EPS,EMP_ESIC,ER_ESIC,PT,LWF_EMP,LWF_ER,ADVANCE,TOTAL_DEDUCTIONS,NET_PAY"]
    for r in s["results"]:
        rows.append(f"{r.emp_id},{r.name},{r.days_in_month},{r.days_worked},{r.ncp_days},{int(r.earned_basic)},{int(r.earned_da)},{int(r.earned_hra)},{int(r.earned_other)},{int(r.gross_earned)},{int(r.pf_wages)},{int(r.employee_pf)},{int(r.employer_epf)},{int(r.employer_eps)},{int(r.employee_esic)},{int(r.employer_esic)},{int(r.professional_tax)},{int(r.lwf_employee)},{int(r.lwf_employer)},{int(r.advance_deduction)},{int(r.total_deductions)},{int(r.net_pay)}")
    fname = f"PayrollRegister_{s['year']}_{s['month']:02d}.csv"
    return StreamingResponse(io.BytesIO("\n".join(rows).encode()), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/download/slip/{session_id}/{emp_id}")
async def download_slip(session_id: str, emp_id: str):
    s = _get_session(session_id)
    result = next((r for r in s["results"] if r.emp_id == emp_id), None)
    if not result:
        raise HTTPException(404, "Employee not found")
    pdf = generate_salary_slip_pdf(result, s["month"], s["year"], s["company_name"])
    fname = f"SalarySlip_{emp_id}_{s['year']}_{s['month']:02d}.pdf"
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/download/all-slips/{session_id}")
async def download_all_slips(session_id: str):
    s = _get_session(session_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in s["results"]:
            pdf = generate_salary_slip_pdf(r, s["month"], s["year"], s["company_name"])
            zf.writestr(f"SalarySlip_{r.emp_id}_{r.name.replace(' ','_')}_{s['year']}_{s['month']:02d}.pdf", pdf)
    buf.seek(0)
    fname = f"SalarySlips_{s['year']}_{s['month']:02d}.zip"
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})
