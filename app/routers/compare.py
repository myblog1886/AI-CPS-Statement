import io
import uuid
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.payroll_engine import calculate_payroll, MONTH_NAMES
from app.ecr_generator import generate_ecr, generate_esic_csv
from app.routers.payroll import parse_file, build_employees, build_summary, SESSIONS

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _parse_newboss_txt(content: bytes) -> dict:
    """Parse New Boss ECR 2.0 .txt file. Returns dict keyed by UAN."""
    result = {}
    for line in content.decode("utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("#")
        if len(parts) < 9:
            continue
        try:
            uan = parts[0].strip()
            result[uan] = {
                "uan":          uan,
                "name":         parts[1].strip() if len(parts) > 1 else "",
                "gross_wages":  float(parts[2]) if parts[2] else 0,
                "epf_wages":    float(parts[3]) if parts[3] else 0,
                "eps_wages":    float(parts[4]) if parts[4] else 0,
                "ncp_days":     int(parts[5])   if parts[5] else 0,
                "employee_pf":  float(parts[7]) if len(parts) > 7 and parts[7] else 0,
                "employer_eps": float(parts[8]) if len(parts) > 8 and parts[8] else 0,
                "employer_epf": float(parts[9]) if len(parts) > 9 and parts[9] else 0,
            }
        except (ValueError, IndexError):
            continue
    return result


def _compare_employee(our: dict, nb: dict) -> dict:
    fields = [
        ("gross_wages",  "gross_earned",  "Gross Wages"),
        ("epf_wages",    "pf_wages",      "EPF Wages"),
        ("employee_pf",  "employee_pf",   "Employee PF"),
        ("employer_epf", "employer_epf",  "Employer EPF"),
        ("employer_eps", "employer_eps",  "Employer EPS"),
        ("ncp_days",     "ncp_days",      "NCP Days"),
    ]
    comparisons = []
    all_match = True
    for nb_field, our_field, label in fields:
        nb_val  = nb.get(nb_field)
        our_val = our.get(our_field)
        if nb_val is None:
            status = "missing_nb"
            all_match = False
        elif our_val is None:
            status = "missing_ours"
            all_match = False
        else:
            diff = abs(float(nb_val) - float(our_val))
            status = "match" if diff <= 1 else "diverge"
            if status == "diverge":
                all_match = False
        comparisons.append({"label": label, "nb_val": nb_val, "our_val": our_val, "status": status})
    return {"comparisons": comparisons, "all_match": all_match}


@router.get("/compare", response_class=HTMLResponse)
async def compare_page(request: Request):
    return templates.TemplateResponse("compare.html", {"request": request})


@router.post("/compare", response_class=HTMLResponse)
async def run_comparison(
    request: Request,
    month: int = Form(...),
    year: int  = Form(...),
    company_name_1: str = Form(""), file_1: Optional[UploadFile] = File(None), nb_file_1: Optional[UploadFile] = File(None),
    company_name_2: str = Form(""), file_2: Optional[UploadFile] = File(None), nb_file_2: Optional[UploadFile] = File(None),
    company_name_3: str = Form(""), file_3: Optional[UploadFile] = File(None), nb_file_3: Optional[UploadFile] = File(None),
    company_name_4: str = Form(""), file_4: Optional[UploadFile] = File(None), nb_file_4: Optional[UploadFile] = File(None),
    company_name_5: str = Form(""), file_5: Optional[UploadFile] = File(None), nb_file_5: Optional[UploadFile] = File(None),
):
    company_inputs = [
        (company_name_1, file_1, nb_file_1),
        (company_name_2, file_2, nb_file_2),
        (company_name_3, file_3, nb_file_3),
        (company_name_4, file_4, nb_file_4),
        (company_name_5, file_5, nb_file_5),
    ]

    companies = []
    errors = []

    for idx, (name, salary_file, nb_file) in enumerate(company_inputs, 1):
        if not salary_file or not salary_file.filename:
            continue
        try:
            content = await salary_file.read()
            df = parse_file(content, salary_file.filename)
            employees = build_employees(df)
            results = [calculate_payroll(emp, month, year) for emp in employees]
            summary  = build_summary(results)

            our_map = {}
            for r in results:
                key = r.uan if r.uan and r.uan not in ("", "nan", "None") else r.emp_id
                our_map[key] = {
                    "name": r.name, "emp_id": r.emp_id, "uan": r.uan,
                    "gross_earned": r.gross_earned, "pf_wages": r.pf_wages,
                    "employee_pf": r.employee_pf, "employer_epf": r.employer_epf,
                    "employer_eps": r.employer_eps, "ncp_days": r.ncp_days,
                }

            nb_map = {}
            if nb_file and nb_file.filename:
                nb_content = await nb_file.read()
                nb_map = _parse_newboss_txt(nb_content)

            # Generate outputs and store in shared SESSIONS so download routes work
            ecr_text  = generate_ecr(results, "MH/MUM/00000", name or f"Company {idx}", month, year)
            esic_text = generate_esic_csv(results, month, year)
            session_id = str(uuid.uuid4())
            SESSIONS[session_id] = {
                "results": results,
                "ecr_text": ecr_text,
                "esic_text": esic_text,
                "company_name": name or f"Company {idx}",
                "establishment_id": "MH/MUM/00000",
                "month": month,
                "year": year,
                "summary": summary,
            }

            all_keys = set(our_map.keys()) | set(nb_map.keys())
            comparison_rows = []
            for key in sorted(all_keys):
                our = our_map.get(key, {})
                nb  = nb_map.get(key, {})
                cmp = _compare_employee(our, nb) if nb_map else {"comparisons": [], "all_match": None}
                comparison_rows.append({
                    "key": key,
                    "name": our.get("name") or nb.get("name") or key,
                    "our": our, "nb": nb, "cmp": cmp,
                })

            match_count   = sum(1 for r in comparison_rows if r["cmp"]["all_match"] is True)
            diverge_count = sum(1 for r in comparison_rows if r["cmp"]["all_match"] is False)

            companies.append({
                "name": name or f"Company {idx}",
                "file": salary_file.filename,
                "session_id": session_id,
                "has_nb": bool(nb_map),
                "results": results,
                "summary": summary,
                "our_map": our_map,
                "nb_map": nb_map,
                "comparison_rows": comparison_rows,
                "match_count": match_count,
                "diverge_count": diverge_count,
                "missing_nb": sum(1 for r in comparison_rows if not r["nb"]),
                "missing_ours": sum(1 for r in comparison_rows if not r["our"]),
            })

        except Exception as exc:
            errors.append({"company": name or f"Company {idx}", "error": str(exc)})

    return templates.TemplateResponse("compare_results.html", {
        "request": request,
        "companies": companies,
        "errors": errors,
        "month": month, "year": year,
        "month_name": MONTH_NAMES[month],
    })
