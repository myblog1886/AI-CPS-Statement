"""
New Labour Codes Compliant Payroll Engine
==========================================
Implements India's four Labour Codes (2019-2020):
  - Code on Wages 2019 (CoW)
  - Code on Social Security 2020 (CoSS)
  - Industrial Relations Code 2020 (IRC)
  - Occupational Safety, Health & Working Conditions Code 2020 (OSH)

Key compliance changes from legacy system:
  1. New "Wages" definition — Basic+DA must be ≥ 50% of CTC (CoW S.2(y))
  2. PF computed on new wages base (CoSS S.3 read with CoW wages definition)
  3. Gratuity eligibility: 1 year for fixed-term employees (CoSS S.53)
  4. OT: 2× rate, 48-hr weekly limit, 12-hr daily shift cap (OSH S.25)
  5. Leave: 1 day per 20 days worked, max 30-day carry-forward (OSH S.32)
  6. ESIC threshold ₹21,000 gross (CoSS S.3 — PENDING gazette for revision)
  7. Gratuity ceiling ₹20 lakhs (CoSS S.53)
"""

from dataclasses import dataclass, field
from typing import Optional

# ── Statutory constants ──────────────────────────────────────────────────────

# Code on Social Security 2020, S.3 — PF
PF_WAGE_CEILING      = 15_000   # EPF/EPS wage ceiling (unchanged)
EPS_MAX_CONTRIBUTION = 1_250    # 8.33% of ₹15,000
EMPLOYEE_PF_RATE     = 0.12
EMPLOYER_EPF_RATE    = 0.0367
EMPLOYER_EPS_RATE    = 0.0833

# Code on Social Security 2020, S.3 — ESIC
# PENDING GAZETTE - draft provisions suggest ceiling may rise to ₹25,000
ESIC_GROSS_CEILING   = 21_000   # Current ceiling (PENDING GAZETTE for revision)
EMPLOYEE_ESIC_RATE   = 0.0075
EMPLOYER_ESIC_RATE   = 0.0325

# Code on Wages 2019, S.2(y) — Wages definition
# Excluded components (HRA, conveyance, OT, bonus) cannot exceed 50% of total wages
# If Basic+DA < 50% of gross CTC → non-compliant; PF base must be adjusted upward
WAGE_RATIO_MINIMUM   = 0.50     # 50% rule

# Code on Social Security 2020, S.53 — Gratuity
GRATUITY_CEILING     = 2_000_000  # ₹20 lakhs maximum
GRATUITY_REGULAR_MIN_YEARS   = 5  # Minimum years for regular employees
GRATUITY_FIXED_TERM_MIN_YEARS = 1  # Minimum years for fixed-term employees (IRC S.2)

# OSH Code 2020, S.25 — Working hours & OT
NORMAL_DAILY_HOURS   = 8
MAX_DAILY_HOURS      = 12       # Absolute shift cap including OT
WEEKLY_HOUR_LIMIT    = 48
OT_RATE_MULTIPLIER   = 2.0     # 2× ordinary wages for OT
# PENDING GAZETTE - max OT hours per day being finalized; using draft of 4 hrs/day
MAX_OT_HOURS_PER_DAY = 4

# OSH Code 2020, S.32 — Leave
LEAVE_EARNED_PER_DAYS_WORKED = 20  # 1 day EL per 20 days worked
# PENDING GAZETTE - carry forward limit; using widely accepted draft of 30 days
MAX_LEAVE_CARRY_FORWARD = 30

# Maharashtra LWF — deducted June & December (unchanged under new codes)
LWF_MONTHS      = {6, 12}
LWF_EMPLOYEE    = 6
LWF_EMPLOYER    = 12

MONTH_NAMES = {
    1: "January",  2: "February", 3: "March",    4: "April",
    5: "May",      6: "June",     7: "July",      8: "August",
    9: "September",10: "October", 11: "November", 12: "December",
}

EMPLOYMENT_TYPES = {"regular", "fixed_term", "gig"}


def _round(v: float) -> float:
    return round(v)


def _pt_maharashtra(gross: float, month: int) -> float:
    """Maharashtra Professional Tax — unchanged under new codes."""
    if gross <= 7_500:
        return 0
    elif gross <= 10_000:
        return 175
    else:
        return 300 if month == 2 else 200


def _lwf_maharashtra(month: int):
    if month in LWF_MONTHS:
        return LWF_EMPLOYEE, LWF_EMPLOYER
    return 0.0, 0.0


# ── Compliance flag types ─────────────────────────────────────────────────────

COMPLIANCE_CODES = {
    "WAGE_RATIO_LOW":           "Basic+DA below 50% of CTC (Code on Wages S.2(y))",
    "PF_BASE_ADJUSTED":         "PF computed on adjusted wages (50% of CTC) per CoW",
    "OT_PAYABLE":               "Overtime hours declared — OT pay at 2× rate (OSH S.25)",
    "OT_DAILY_LIMIT_BREACH":    "Daily hours exceed 12-hour shift cap (OSH S.25)",
    "OT_WEEKLY_LIMIT_BREACH":   "Weekly hours exceed 48-hour limit (OSH S.25)",
    "GRATUITY_ELIGIBLE_FTE":    "Fixed-term employee ≥1 year — gratuity accruing (CoSS S.53)",
    "GRATUITY_ELIGIBLE_REGULAR":"Regular employee ≥5 years — gratuity accruing (CoSS S.53)",
    "ESIC_BOUNDARY":            "Gross within ₹500 of ESIC ceiling — monitor monthly",
    "LEAVE_CARRY_FORWARD_CAP":  "Carry-forward exceeds 30-day limit (OSH S.32 — PENDING GAZETTE)",
    "GIG_WORKER_COVERAGE":      "Gig/platform worker — social security coverage pending state scheme (CoSS S.113-114)",
}


@dataclass
class EmployeeInputLC:
    emp_id: str
    name: str
    uan: str
    pf_number: str
    esic_number: str
    basic: float
    da: float
    hra: float
    special_allowance: float      # Universally-paid special allowance (part of CTC)
    other_allowances: float       # Other allowances (conveyance, medical, etc.)
    ctc_monthly: float            # Monthly CTC — if 0, computed from gross components
    days_in_month: int
    days_worked: int
    employment_type: str          # regular / fixed_term / gig
    years_of_service: float       # Completed years of service (for gratuity)
    ot_hours_month: float         # Overtime hours logged this month
    daily_avg_hours: float        # Average working hours per day this month (incl OT)
    leave_balance_opening: float  # Opening leave balance (days) for carry-forward check
    advance_deduction: float = 0.0
    bank_account: str = ""
    ifsc_code: str = ""
    designation: str = ""
    department: str = ""


@dataclass
class ComplianceFlag:
    code: str
    severity: str          # critical / warning / info
    description: str
    detail: str            # quantified detail


@dataclass
class PayrollResultLC:
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
    employment_type: str
    years_of_service: float

    # Earnings (prorated)
    earned_basic: float
    earned_da: float
    earned_hra: float
    earned_special: float
    earned_other: float
    gross_earned: float

    # Wage ratio compliance (Code on Wages S.2(y))
    core_wages_earned: float        # Basic + DA (core wages)
    ctc_gross_monthly: float        # CTC proxy for ratio check
    wage_ratio_actual: float        # core_wages / ctc_gross
    wage_ratio_compliant: bool      # True if ≥ 50%
    adjusted_wages: float           # max(core_wages, 50% CTC) — PF base

    # PF (computed on adjusted wages, not just basic+da if ratio is low)
    pf_wages: float                 # min(adjusted_wages, 15,000)
    employee_pf: float
    employer_epf: float
    employer_eps: float
    edli_wages: float
    pf_base_adjusted: bool          # True if PF base was lifted due to 50% rule

    # ESIC
    esic_applicable: bool
    employee_esic: float
    employer_esic: float

    # PT
    professional_tax: float

    # LWF
    lwf_employee: float
    lwf_employer: float

    # OT (OSH Code S.25)
    ot_hours_month: float
    ot_pay: float
    ot_compliant: bool              # True if within limits
    daily_avg_hours: float

    # Gratuity (CoSS S.53)
    gratuity_eligible: bool
    monthly_gratuity_accrual: float # for display — what accrues this month
    gratuity_total_accrued: float   # total accrued based on years_of_service

    # Leave (OSH Code S.32)
    leave_earned_this_month: float
    leave_carry_forward_opening: float
    leave_carry_forward_net: float
    leave_carry_capped: bool

    # Other
    advance_deduction: float
    total_deductions: float
    net_pay: float

    # Compliance
    flags: list  # list[ComplianceFlag]


# ── Core calculation ───────────────────────────────────────────────────────────

def calculate_payroll_lc(emp: EmployeeInputLC, month: int, year: int) -> PayrollResultLC:
    factor = emp.days_worked / emp.days_in_month

    # ── 1. Prorate earnings ──────────────────────────────────────────────────
    earned_basic   = _round(emp.basic   * factor)
    earned_da      = _round(emp.da      * factor)
    earned_hra     = _round(emp.hra     * factor)
    earned_special = _round(emp.special_allowance * factor)
    earned_other   = _round(emp.other_allowances  * factor)
    gross_earned   = earned_basic + earned_da + earned_hra + earned_special + earned_other

    # ── 2. Code on Wages S.2(y) — 50% wage ratio check ─────────────────────
    # CTC proxy = gross (if ctc_monthly not provided)
    ctc_gross = emp.ctc_monthly if emp.ctc_monthly > 0 else (
        emp.basic + emp.da + emp.hra + emp.special_allowance + emp.other_allowances
    )
    ctc_gross_earned = ctc_gross * factor      # prorated CTC for the month

    # Core wages (Basic + DA — what the Code treats as "wages")
    core_wages_earned   = earned_basic + earned_da
    wage_ratio_actual   = core_wages_earned / ctc_gross_earned if ctc_gross_earned > 0 else 1.0
    wage_ratio_compliant = wage_ratio_actual >= WAGE_RATIO_MINIMUM

    # If non-compliant, PF base must be adjusted upward to 50% of CTC
    adjusted_wages  = max(core_wages_earned, WAGE_RATIO_MINIMUM * ctc_gross_earned)
    pf_base_adjusted = not wage_ratio_compliant

    # ── 3. PF — computed on adjusted wages (CoSS + CoW) ─────────────────────
    pf_wages    = min(adjusted_wages, PF_WAGE_CEILING)
    employee_pf = _round(pf_wages * EMPLOYEE_PF_RATE)
    employer_eps= min(_round(pf_wages * EMPLOYER_EPS_RATE), EPS_MAX_CONTRIBUTION)
    employer_epf= _round(pf_wages * EMPLOYER_EPF_RATE)
    edli_wages  = pf_wages

    # ── 4. ESIC (CoSS S.3 — ceiling ₹21,000, PENDING GAZETTE for revision) ─
    esic_applicable = gross_earned <= ESIC_GROSS_CEILING
    employee_esic   = _round(gross_earned * EMPLOYEE_ESIC_RATE) if esic_applicable else 0
    employer_esic   = _round(gross_earned * EMPLOYER_ESIC_RATE) if esic_applicable else 0

    # ── 5. Professional Tax (Maharashtra — unchanged) ────────────────────────
    pt = _pt_maharashtra(gross_earned, month)

    # ── 6. LWF Maharashtra (unchanged) ──────────────────────────────────────
    lwf_emp, lwf_er = _lwf_maharashtra(month)

    # ── 7. OT Calculation (OSH Code S.25) ────────────────────────────────────
    # Hourly rate = (core_wages / 26 working days / 8 hours)
    daily_wage = core_wages_earned / emp.days_worked if emp.days_worked > 0 else 0
    hourly_wage = daily_wage / NORMAL_DAILY_HOURS
    ot_pay = _round(hourly_wage * OT_RATE_MULTIPLIER * emp.ot_hours_month)
    ot_daily_breach   = emp.daily_avg_hours > MAX_DAILY_HOURS
    ot_weekly_approx  = emp.daily_avg_hours * (emp.days_worked / 4.33)   # rough weekly avg
    ot_weekly_breach  = ot_weekly_approx > WEEKLY_HOUR_LIMIT
    ot_compliant      = not ot_daily_breach and not ot_weekly_breach

    # ── 8. Gratuity Accrual (CoSS S.53) ─────────────────────────────────────
    # Wages for gratuity = wages as per new definition (core_wages)
    # Formula: (monthly_wages × 15 / 26) per year of service
    if emp.employment_type == "fixed_term":
        gratuity_eligible = emp.years_of_service >= GRATUITY_FIXED_TERM_MIN_YEARS
    elif emp.employment_type == "regular":
        gratuity_eligible = emp.years_of_service >= GRATUITY_REGULAR_MIN_YEARS
    else:
        gratuity_eligible = False   # gig workers — PENDING gazette

    gratuity_wages = core_wages_earned   # use core wages (Basic+DA after proration)
    gratuity_total = min(
        (gratuity_wages * 15 / 26) * emp.years_of_service,
        GRATUITY_CEILING,
    ) if gratuity_eligible else 0.0
    monthly_gratuity_accrual = _round(
        gratuity_wages * 15 / 26 / 12
    ) if gratuity_eligible else 0.0

    # ── 9. Leave Accrual (OSH Code S.32) ─────────────────────────────────────
    leave_earned = round(emp.days_worked / LEAVE_EARNED_PER_DAYS_WORKED, 2)
    leave_net    = emp.leave_balance_opening + leave_earned
    leave_capped = leave_net > MAX_LEAVE_CARRY_FORWARD
    leave_net_capped = min(leave_net, MAX_LEAVE_CARRY_FORWARD) if leave_capped else leave_net

    # ── 10. Net Pay ──────────────────────────────────────────────────────────
    total_deductions = (
        employee_pf + employee_esic + pt + lwf_emp + emp.advance_deduction
    )
    net_pay = gross_earned + ot_pay - total_deductions

    # ── 11. Compliance Flags ──────────────────────────────────────────────────
    flags = []

    if not wage_ratio_compliant:
        flags.append(ComplianceFlag(
            code="WAGE_RATIO_LOW",
            severity="critical",
            description=COMPLIANCE_CODES["WAGE_RATIO_LOW"],
            detail=(
                f"Basic+DA = ₹{int(core_wages_earned):,} "
                f"({wage_ratio_actual*100:.1f}% of CTC). "
                f"Minimum required: 50%. "
                f"Difference: ₹{int(adjusted_wages - core_wages_earned):,} must be reclassified as wages."
            ),
        ))

    if pf_base_adjusted:
        flags.append(ComplianceFlag(
            code="PF_BASE_ADJUSTED",
            severity="warning",
            description=COMPLIANCE_CODES["PF_BASE_ADJUSTED"],
            detail=(
                f"PF wages adjusted from ₹{int(core_wages_earned):,} to "
                f"₹{int(pf_wages):,} (50% of CTC = ₹{int(adjusted_wages):,}, "
                f"capped at ₹15,000 ceiling)."
            ),
        ))

    if emp.ot_hours_month > 0:
        flags.append(ComplianceFlag(
            code="OT_PAYABLE",
            severity="info",
            description=COMPLIANCE_CODES["OT_PAYABLE"],
            detail=(
                f"{emp.ot_hours_month:.1f} OT hours @ 2× rate. "
                f"OT pay = ₹{int(ot_pay):,}."
            ),
        ))

    if ot_daily_breach:
        flags.append(ComplianceFlag(
            code="OT_DAILY_LIMIT_BREACH",
            severity="critical",
            description=COMPLIANCE_CODES["OT_DAILY_LIMIT_BREACH"],
            detail=(
                f"Avg {emp.daily_avg_hours:.1f} hrs/day exceeds 12-hr cap. "
                f"OSH Code S.25 — maximum shift including OT is 12 hours."
            ),
        ))

    if ot_weekly_breach:
        flags.append(ComplianceFlag(
            code="OT_WEEKLY_LIMIT_BREACH",
            severity="critical",
            description=COMPLIANCE_CODES["OT_WEEKLY_LIMIT_BREACH"],
            detail=(
                f"Estimated weekly hours ≈{ot_weekly_approx:.0f}. "
                f"Limit: 48 hrs/week (OSH Code S.25)."
            ),
        ))

    if emp.employment_type == "fixed_term" and gratuity_eligible:
        flags.append(ComplianceFlag(
            code="GRATUITY_ELIGIBLE_FTE",
            severity="info",
            description=COMPLIANCE_CODES["GRATUITY_ELIGIBLE_FTE"],
            detail=(
                f"{emp.years_of_service:.1f} years completed. "
                f"Total gratuity accrued = ₹{int(gratuity_total):,}. "
                f"Monthly accrual = ₹{int(monthly_gratuity_accrual):,}."
            ),
        ))
    elif emp.employment_type == "regular" and gratuity_eligible:
        flags.append(ComplianceFlag(
            code="GRATUITY_ELIGIBLE_REGULAR",
            severity="info",
            description=COMPLIANCE_CODES["GRATUITY_ELIGIBLE_REGULAR"],
            detail=(
                f"{emp.years_of_service:.1f} years completed. "
                f"Total gratuity accrued = ₹{int(gratuity_total):,}. "
                f"Monthly accrual = ₹{int(monthly_gratuity_accrual):,}."
            ),
        ))

    if abs(gross_earned - ESIC_GROSS_CEILING) <= 500 and gross_earned <= ESIC_GROSS_CEILING:
        flags.append(ComplianceFlag(
            code="ESIC_BOUNDARY",
            severity="warning",
            description=COMPLIANCE_CODES["ESIC_BOUNDARY"],
            detail=(
                f"Gross ₹{int(gross_earned):,} — only ₹{int(ESIC_GROSS_CEILING - gross_earned):,} "
                f"below ₹21,000 ceiling. Any increment may remove ESIC coverage."
            ),
        ))

    if leave_capped:
        flags.append(ComplianceFlag(
            code="LEAVE_CARRY_FORWARD_CAP",
            severity="warning",
            description=COMPLIANCE_CODES["LEAVE_CARRY_FORWARD_CAP"],
            detail=(
                f"Carry-forward would be {leave_net:.1f} days; "
                f"capped at {MAX_LEAVE_CARRY_FORWARD} days per OSH Code S.32 "
                f"(PENDING GAZETTE — draft provision)."
            ),
        ))

    if emp.employment_type == "gig":
        flags.append(ComplianceFlag(
            code="GIG_WORKER_COVERAGE",
            severity="warning",
            description=COMPLIANCE_CODES["GIG_WORKER_COVERAGE"],
            detail=(
                "CoSS S.113-114 mandates social security for gig/platform workers. "
                "Central/state scheme rules PENDING notification. "
                "Employer should monitor for scheme launch and enrol promptly."
            ),
        ))

    return PayrollResultLC(
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
        employment_type=emp.employment_type,
        years_of_service=emp.years_of_service,
        earned_basic=earned_basic,
        earned_da=earned_da,
        earned_hra=earned_hra,
        earned_special=earned_special,
        earned_other=earned_other,
        gross_earned=gross_earned,
        core_wages_earned=core_wages_earned,
        ctc_gross_monthly=ctc_gross_earned,
        wage_ratio_actual=wage_ratio_actual,
        wage_ratio_compliant=wage_ratio_compliant,
        adjusted_wages=adjusted_wages,
        pf_wages=pf_wages,
        employee_pf=employee_pf,
        employer_epf=employer_epf,
        employer_eps=employer_eps,
        edli_wages=edli_wages,
        pf_base_adjusted=pf_base_adjusted,
        esic_applicable=esic_applicable,
        employee_esic=employee_esic,
        employer_esic=employer_esic,
        professional_tax=pt,
        lwf_employee=lwf_emp,
        lwf_employer=lwf_er,
        ot_hours_month=emp.ot_hours_month,
        ot_pay=ot_pay,
        ot_compliant=ot_compliant,
        daily_avg_hours=emp.daily_avg_hours,
        gratuity_eligible=gratuity_eligible,
        monthly_gratuity_accrual=monthly_gratuity_accrual,
        gratuity_total_accrued=gratuity_total,
        leave_earned_this_month=leave_earned,
        leave_carry_forward_opening=emp.leave_balance_opening,
        leave_carry_forward_net=leave_net_capped,
        leave_carry_capped=leave_capped,
        advance_deduction=emp.advance_deduction,
        total_deductions=total_deductions,
        net_pay=net_pay,
        flags=flags,
    )


# ── Summary builder ───────────────────────────────────────────────────────────

def build_summary_lc(results: list) -> dict:
    total_flags_critical = sum(
        sum(1 for f in r.flags if f.severity == "critical") for r in results
    )
    total_flags_warning  = sum(
        sum(1 for f in r.flags if f.severity == "warning")  for r in results
    )
    non_compliant_wage   = sum(1 for r in results if not r.wage_ratio_compliant)
    ot_employees         = sum(1 for r in results if r.ot_hours_month > 0)
    gratuity_eligible    = sum(1 for r in results if r.gratuity_eligible)
    fte_employees        = sum(1 for r in results if r.employment_type == "fixed_term")
    gig_employees        = sum(1 for r in results if r.employment_type == "gig")

    return {
        "total_employees":      len(results),
        "esic_count":           sum(1 for r in results if r.esic_applicable),
        "total_gross":          sum(r.gross_earned        for r in results),
        "total_ot_pay":         sum(r.ot_pay              for r in results),
        "total_net":            sum(r.net_pay             for r in results),
        "total_employee_pf":    sum(r.employee_pf         for r in results),
        "total_employer_epf":   sum(r.employer_epf        for r in results),
        "total_employer_eps":   sum(r.employer_eps        for r in results),
        "total_employer_pf":    sum(r.employer_epf + r.employer_eps for r in results),
        "total_pf_challan":     sum(r.employee_pf + r.employer_epf + r.employer_eps for r in results),
        "total_employee_esic":  sum(r.employee_esic       for r in results),
        "total_employer_esic":  sum(r.employer_esic       for r in results),
        "total_esic_challan":   sum(r.employee_esic + r.employer_esic for r in results),
        "total_pt":             sum(r.professional_tax    for r in results),
        "total_lwf_employee":   sum(r.lwf_employee        for r in results),
        "total_lwf_employer":   sum(r.lwf_employer        for r in results),
        "total_gratuity_accrued": sum(r.gratuity_total_accrued for r in results),
        # Compliance metrics
        "compliance_critical":  total_flags_critical,
        "compliance_warning":   total_flags_warning,
        "non_compliant_wage":   non_compliant_wage,
        "ot_employees":         ot_employees,
        "gratuity_eligible":    gratuity_eligible,
        "fte_employees":        fte_employees,
        "gig_employees":        gig_employees,
    }
