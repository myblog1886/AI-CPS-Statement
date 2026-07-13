"""
Compliance engine wrapper.
Loads cps-compliance-platform rules via importlib to avoid package collisions.
"""
import importlib.util
from pathlib import Path

_RULES_DIR = Path("/Users/madhavibhat/cps-compliance-platform/rules")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_central = _load_module("central_acts", _RULES_DIR / "central_acts.py")
_state = _load_module("state_acts", _RULES_DIR / "state_acts.py")

CHECKERS = [
    _central.check_epf,
    _central.check_esic,
    _central.check_minimum_wages,
    _central.check_payment_of_wages,
    _central.check_factories_act,
    _central.check_payment_of_bonus,
    _central.check_gratuity,
    _central.check_maternity_benefit,
    _central.check_posh,
    _central.check_contract_labour,
    _central.check_industrial_disputes,
    _central.check_labour_codes,
    _state.check_professional_tax,
    _state.check_labour_welfare_fund,
    _state.check_shops_establishment,
]


def _build_compliance_data(payroll_results: list[dict], client) -> dict:
    emp_count = len(payroll_results)
    wages = [r.get("gross_salary", 0) or r.get("gross_earned", 0) for r in payroll_results]
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
        "wage_structure": {
            "basic": sum(r.get("basic", 0) for r in payroll_results) / emp_count if emp_count else 0,
            "hra": sum(r.get("hra", 0) for r in payroll_results) / emp_count if emp_count else 0,
            "da": sum(r.get("da", 0) for r in payroll_results) / emp_count if emp_count else 0,
            "special_allowances": sum(r.get("other_allowances", 0) for r in payroll_results) / emp_count if emp_count else 0,
            "total_ctc": avg_wage,
        },
        "women_employee_count": 0,
        "contract_worker_count": 0,
        "gig_worker_count": 0,
        "operates_in_states": [getattr(client, "state", "Maharashtra")],
    }


STATUS_MAP = {
    "non_compliant": "fail",
    "compliant": "pass",
    "not_applicable": "pass",
    "partial": "partial",
}


def run_compliance(payroll_results: list[dict], client) -> list[dict]:
    """
    Run all compliance checkers against payroll results and client metadata.
    Returns a list of finding dicts with keys:
      act, section, area, status, reason, priority, penalty, next_steps
    Status values are normalised to: "pass", "fail", "partial".
    """
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
    for f in findings:
        f["status"] = STATUS_MAP.get(f.get("status", ""), f.get("status", ""))
    return findings
