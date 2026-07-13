"""
Payroll engine wrapper.
Loads payroll_v2/app/payroll_engine.py via importlib to avoid the `app/`
package name collision between payroll_crm and payroll_v2.
"""
import importlib.util
from dataclasses import asdict
from pathlib import Path


def _load_payroll_engine():
    spec = importlib.util.spec_from_file_location(
        "payroll_engine_v2",
        Path("/Users/madhavibhat/payroll_v2/app/payroll_engine.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_engine = _load_payroll_engine()
EmployeeInput = _engine.EmployeeInput
calculate_payroll = _engine.calculate_payroll


def run_payroll(employees: list[dict], month: int, year: int) -> list[dict]:
    """
    Run payroll calculation for a list of employee dicts.
    Returns a list of PayrollResult dicts (via dataclasses.asdict).
    """
    results = []
    for emp_data in employees:
        emp = EmployeeInput(
            emp_id=str(emp_data.get("emp_id") or ""),
            name=str(emp_data.get("name") or ""),
            uan=str(emp_data.get("uan") or ""),
            pf_number=str(emp_data.get("pf_number") or ""),
            esic_number=str(emp_data.get("esic_number") or ""),
            basic=float(emp_data.get("basic") or 0),
            da=float(emp_data.get("da") or 0),
            hra=float(emp_data.get("hra") or 0),
            other_allowances=float(emp_data.get("other_allowances") or 0),
            days_in_month=int(emp_data.get("days_in_month") or 30),
            days_worked=int(emp_data.get("days_worked") or 0),
            advance_deduction=float(emp_data.get("advance_deduction") or 0),
            bank_account=str(emp_data.get("bank_account") or ""),
            ifsc_code=str(emp_data.get("ifsc_code") or ""),
            designation=str(emp_data.get("designation") or ""),
            department=str(emp_data.get("department") or ""),
        )
        result = calculate_payroll(emp, month, year)
        results.append(asdict(result))
    return results
