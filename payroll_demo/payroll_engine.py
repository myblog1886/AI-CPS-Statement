"""
India Payroll Engine — Maharashtra
Handles PF, ESIC, PT, LWF statutory calculations.
"""
from dataclasses import dataclass, field
from typing import Optional

# ── Statutory constants ──────────────────────────────────────────────────────
PF_WAGE_CEILING      = 15_000   # EPF/EPS wage ceiling (EPFO)
EPS_MAX_CONTRIBUTION = 1_250    # 8.33% of 15,000
ESIC_GROSS_CEILING   = 21_000   # Above this → ESIC not applicable

EMPLOYEE_PF_RATE   = 0.12
EMPLOYER_EPF_RATE  = 0.0367
EMPLOYER_EPS_RATE  = 0.0833

EMPLOYEE_ESIC_RATE = 0.0075
EMPLOYER_ESIC_RATE = 0.0325

# Maharashtra LWF — deducted in June (6) and December (12)
LWF_MONTHS         = {6, 12}
LWF_EMPLOYEE       = 6    # ₹6 per half-year
LWF_EMPLOYER       = 12   # ₹12 per half-year

MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May",     6: "June",     7: "July",  8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


def _round(amount: float) -> float:
    return round(amount)


def _pt_maharashtra(gross: float, month: int) -> float:
    """Maharashtra Professional Tax slabs (FY 2024-25)."""
    if gross <= 7_500:
        return 0
    elif gross <= 10_000:
        return 175
    else:
        return 300 if month == 2 else 200   # February slab is ₹300


def _lwf_maharashtra(month: int) -> tuple[float, float]:
    """Returns (employee_lwf, employer_lwf). Non-zero only in June & December."""
    if month in LWF_MONTHS:
        return LWF_EMPLOYEE, LWF_EMPLOYER
    return 0.0, 0.0


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class EmployeeInput:
    emp_id: str
    name: str
    uan: str
    pf_number: str
    esic_number: str
    basic: float
    da: float
    hra: float
    other_allowances: float
    days_in_month: int
    days_worked: int
    advance_deduction: float = 0.0
    bank_account: str = ""
    ifsc_code: str = ""
    designation: str = ""
    department: str = ""


@dataclass
class PayrollResult:
    # Identity
    emp_id: str
    name: str
    uan: str
    pf_number: str
    esic_number: str
    days_in_month: int
    days_worked: int
    ncp_days: int
    bank_account: str
    ifsc_code: str
    designation: str
    department: str

    # Earnings (prorated)
    earned_basic: float
    earned_da: float
    earned_hra: float
    earned_other: float
    gross_earned: float

    # PF
    pf_wages: float
    employee_pf: float
    employer_epf: float
    employer_eps: float
    edli_wages: float

    # ESIC
    esic_applicable: bool
    employee_esic: float
    employer_esic: float

    # PT
    professional_tax: float

    # LWF (Maharashtra)
    lwf_employee: float
    lwf_employer: float

    # Other
    advance_deduction: float

    # Totals
    total_deductions: float
    net_pay: float


# ── Core calculation ──────────────────────────────────────────────────────────

def calculate_payroll(emp: EmployeeInput, month: int, year: int) -> PayrollResult:
    factor = emp.days_worked / emp.days_in_month

    # ── Prorate earnings ─────────────────────────────────────────────────────
    earned_basic = _round(emp.basic * factor)
    earned_da    = _round(emp.da    * factor)
    earned_hra   = _round(emp.hra   * factor)
    earned_other = _round(emp.other_allowances * factor)
    gross_earned = earned_basic + earned_da + earned_hra + earned_other

    # ── PF (capped at ₹15,000 per EPFO wage ceiling) ────────────────────────
    pf_wages      = min(earned_basic + earned_da, PF_WAGE_CEILING)
    employee_pf   = _round(pf_wages * EMPLOYEE_PF_RATE)
    employer_eps  = min(_round(pf_wages * EMPLOYER_EPS_RATE), EPS_MAX_CONTRIBUTION)
    employer_epf  = _round(pf_wages * EMPLOYER_EPF_RATE)
    edli_wages    = pf_wages

    # ── ESIC ─────────────────────────────────────────────────────────────────
    esic_applicable = gross_earned <= ESIC_GROSS_CEILING
    employee_esic   = _round(gross_earned * EMPLOYEE_ESIC_RATE) if esic_applicable else 0
    employer_esic   = _round(gross_earned * EMPLOYER_ESIC_RATE) if esic_applicable else 0

    # ── Professional Tax (Maharashtra) ───────────────────────────────────────
    pt = _pt_maharashtra(gross_earned, month)

    # ── LWF (Maharashtra) ────────────────────────────────────────────────────
    lwf_emp, lwf_er = _lwf_maharashtra(month)

    # ── Net pay ──────────────────────────────────────────────────────────────
    total_deductions = employee_pf + employee_esic + pt + lwf_emp + emp.advance_deduction
    net_pay          = gross_earned - total_deductions

    return PayrollResult(
        emp_id=emp.emp_id,
        name=emp.name,
        uan=emp.uan,
        pf_number=emp.pf_number,
        esic_number=emp.esic_number,
        days_in_month=emp.days_in_month,
        days_worked=emp.days_worked,
        ncp_days=emp.days_in_month - emp.days_worked,
        bank_account=emp.bank_account,
        ifsc_code=emp.ifsc_code,
        designation=emp.designation,
        department=emp.department,
        earned_basic=earned_basic,
        earned_da=earned_da,
        earned_hra=earned_hra,
        earned_other=earned_other,
        gross_earned=gross_earned,
        pf_wages=pf_wages,
        employee_pf=employee_pf,
        employer_epf=employer_epf,
        employer_eps=employer_eps,
        edli_wages=edli_wages,
        esic_applicable=esic_applicable,
        employee_esic=employee_esic,
        employer_esic=employer_esic,
        professional_tax=pt,
        lwf_employee=lwf_emp,
        lwf_employer=lwf_er,
        advance_deduction=emp.advance_deduction,
        total_deductions=total_deductions,
        net_pay=net_pay,
    )


# ── Audit / variance check ────────────────────────────────────────────────────

AUDIT_THRESHOLDS = {
    "gross":       0.05,   # 5% change triggers a flag
    "employee_pf": 0.10,
    "net_pay":     0.05,
    "days_worked": 0,      # any change in days flags
}

def audit_variance(
    prev: list[PayrollResult],
    curr: list[PayrollResult],
) -> list[dict]:
    """Compare current payroll vs previous month. Returns list of flag dicts."""
    prev_map = {r.emp_id: r for r in prev}
    curr_map = {r.emp_id: r for r in curr}
    flags = []

    for eid, c in curr_map.items():
        if eid not in prev_map:
            flags.append({
                "emp_id": eid, "name": c.name,
                "type": "NEW_EMPLOYEE",
                "field": "—", "prev": "—", "curr": "—", "change_pct": "—",
                "severity": "info",
            })
            continue
        p = prev_map[eid]

        checks = [
            ("Gross Salary",  p.gross_earned,  c.gross_earned,  0.05),
            ("Net Pay",       p.net_pay,        c.net_pay,       0.05),
            ("Employee PF",   p.employee_pf,    c.employee_pf,   0.10),
            ("Days Worked",   p.days_worked,    c.days_worked,   0.0),
            ("Basic",         p.earned_basic,   c.earned_basic,  0.05),
        ]
        for label, pval, cval, threshold in checks:
            if pval == 0:
                continue
            pct = abs(cval - pval) / pval
            if pct > threshold or (threshold == 0.0 and pval != cval):
                flags.append({
                    "emp_id": eid,
                    "name":   c.name,
                    "type":   "VARIANCE",
                    "field":  label,
                    "prev":   f"₹{pval:,.0f}" if label != "Days Worked" else str(int(pval)),
                    "curr":   f"₹{cval:,.0f}" if label != "Days Worked" else str(int(cval)),
                    "change_pct": f"{pct*100:+.1f}%",
                    "severity": "high" if pct > 0.15 else "medium",
                })

    for eid, p in prev_map.items():
        if eid not in curr_map:
            flags.append({
                "emp_id": eid, "name": p.name,
                "type": "MISSING_EMPLOYEE",
                "field": "—", "prev": "—", "curr": "—", "change_pct": "—",
                "severity": "high",
            })

    return flags
