"""
EPFO ECR 2.0 (Electronic Challan-cum-Return) file generator.

Format reference: EPFO Unified Portal ECR specification.
Each member row: UAN~#NAME~#GROSS~#EPF_WAGES~#EPS_WAGES~#EDLI_WAGES~#EPF_CONT~#EPS_CONT~#EPF_EPS_DIFF~#NCP_DAYS~#REFUND
"""
from typing import List
from app.payroll_engine import PayrollResult


def generate_ecr(
    results: List[PayrollResult],
    establishment_id: str,
    establishment_name: str,
    month: int,
    year: int,
) -> str:
    lines = []

    # ── File header ───────────────────────────────────────────────────────────
    lines.append("#~#")
    lines.append(f"EST_ID~#{establishment_id}")
    lines.append(f"EST_NAME~#{establishment_name}")
    lines.append(f"MONTH~#{month:02d}")
    lines.append(f"YEAR~#{year}")
    lines.append(f"TOTAL_MEMBERS~#{len(results)}")
    lines.append("#~#")

    # ── Member detail rows ────────────────────────────────────────────────────
    for r in results:
        # Total EPF contribution = employee share + employer EPF share
        epf_contribution = r.employee_pf + r.employer_epf
        eps_contribution = r.employer_eps
        epf_eps_diff     = epf_contribution - eps_contribution

        row = "~#".join([
            r.uan,
            r.name,
            str(int(r.gross_earned)),
            str(int(r.pf_wages)),    # EPF wages
            str(int(r.pf_wages)),    # EPS wages (same ceiling)
            str(int(r.edli_wages)),  # EDLI wages
            str(int(epf_contribution)),
            str(int(eps_contribution)),
            str(int(epf_eps_diff)),
            str(r.ncp_days),
            "0",                     # Refund of advances
        ])
        lines.append(row)

    return "\n".join(lines)


def generate_esic_csv(results: List[PayrollResult], month: int, year: int) -> str:
    """ESIC monthly contribution file (CSV format for portal upload)."""
    lines = [
        "IP_NUMBER,IP_NAME,GROSS_WAGES,EMPLOYER_CONTRIBUTION,EMPLOYEE_CONTRIBUTION,TOTAL_CONTRIBUTION"
    ]
    for r in results:
        if r.esic_applicable:
            total = r.employee_esic + r.employer_esic
            lines.append(
                f"{r.esic_number},{r.name},"
                f"{int(r.gross_earned)},{int(r.employer_esic)},"
                f"{int(r.employee_esic)},{int(total)}"
            )
    return "\n".join(lines)
