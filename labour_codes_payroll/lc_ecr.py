"""
ECR 2.0 and ESIC CSV generator for New Labour Codes Payroll Tool.
Structure mirrors existing ecr_generator.py but uses new wages definition.
"""
from lc_engine import PayrollResultLC, MONTH_NAMES


def generate_ecr_lc(
    results: list,
    establishment_id: str,
    establishment_name: str,
    month: int,
    year: int,
) -> str:
    """
    Generate EPFO ECR 2.0 format file.
    PF wages are now computed on the CoW-adjusted wages base (not just basic+DA
    if ratio was non-compliant), so ECR reflects the corrected PF contribution.
    """
    lines = []
    lines.append("#~#")
    lines.append(f"EST_ID~#{establishment_id}")
    lines.append(f"EST_NAME~#{establishment_name}")
    lines.append(f"MONTH~#{month:02d}")
    lines.append(f"YEAR~#{year}")
    lines.append(f"TOTAL_MEMBERS~#{len(results)}")
    lines.append("#~#")

    for r in results:
        uan     = r.uan or "0"
        gross   = int(r.gross_earned)
        pf_wage = int(r.pf_wages)
        emp_pf  = int(r.employee_pf)
        er_epf  = int(r.employer_epf)
        er_eps  = int(r.employer_eps)
        total_pf_remitted = emp_pf + er_epf
        eps_remitted       = er_eps
        diff_epf_eps       = total_pf_remitted - eps_remitted
        ncp     = r.ncp_days
        lines.append(
            f"{uan}~#{r.name}~#{gross}~#{pf_wage}~#{pf_wage}~#{pf_wage}~#"
            f"{total_pf_remitted}~#{eps_remitted}~#{diff_epf_eps}~#{ncp}~#0"
        )

    return "\n".join(lines)


def generate_esic_csv_lc(results: list, month: int, year: int) -> str:
    """
    ESIC monthly contribution CSV.
    Threshold: ₹21,000 gross (Code on Social Security 2020, S.3 — PENDING GAZETTE for revision).
    """
    rows = ["IP_NUMBER,EMPLOYEE_NAME,GROSS_WAGES,EMPLOYEE_ESIC_0.75PCT,EMPLOYER_ESIC_3.25PCT,TOTAL_ESIC"]
    month_name = MONTH_NAMES[month]
    for r in results:
        if not r.esic_applicable:
            continue
        total = r.employee_esic + r.employer_esic
        rows.append(
            f"{r.esic_number or 'N/A'},{r.name},"
            f"{int(r.gross_earned)},{int(r.employee_esic)},"
            f"{int(r.employer_esic)},{int(total)}"
        )
    return "\n".join(rows)
