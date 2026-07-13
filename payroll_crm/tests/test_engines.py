import sys
sys.path.insert(0, "/Users/madhavibhat/payroll_crm")

from app.engines.payroll import run_payroll
from app.engines.compliance import run_compliance

SAMPLE_EMPLOYEES = [
    {
        "emp_id": "E001", "name": "Rahul Sharma", "uan": "101234567801",
        "pf_number": "MH/MUM/001/001", "esic_number": "3001234501",
        "basic": 18000, "da": 3600, "hra": 7200, "other_allowances": 2200,
        "days_in_month": 31, "days_worked": 31, "advance_deduction": 0,
        "bank_account": "112233445501", "ifsc_code": "HDFC0001111",
        "designation": "Engineer", "department": "Tech"
    }
]


def test_run_payroll_returns_list_of_dicts():
    results = run_payroll(SAMPLE_EMPLOYEES, month=6, year=2026)
    assert isinstance(results, list)
    assert len(results) == 1
    r = results[0]
    assert "net_pay" in r
    assert "employee_pf" in r
    assert r["net_pay"] > 0


def test_run_payroll_pf_calculation():
    results = run_payroll(SAMPLE_EMPLOYEES, month=6, year=2026)
    # 12% of min(18000, 15000) = 1800
    assert results[0]["employee_pf"] == 1800


def test_run_compliance_returns_list():
    results = run_payroll(SAMPLE_EMPLOYEES, month=6, year=2026)

    class FakeClient:
        state = "Maharashtra"
        industry_type = "IT"
        headcount = 25
        establishment_id = "MH/MUM/001"

    findings = run_compliance(results, FakeClient())
    assert isinstance(findings, list)
    assert len(findings) > 0
    assert "status" in findings[0]
    assert findings[0]["status"] in ("pass", "fail", "partial")
