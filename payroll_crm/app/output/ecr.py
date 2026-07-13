from pathlib import Path
import io


def generate_ecr(payroll_results: list[dict], month: int, year: int) -> bytes:
    """Generate EPFO ECR 2.0 pipe-delimited TXT. Returns bytes."""
    lines = []
    # Header
    lines.append(f"#~#MONTH#{month:02d}#{year}#~#")
    for r in payroll_results:
        uan = r.get("uan", "") or ""
        epf_wages = int(min(r.get("basic", 0) + r.get("da", 0), 15000))
        eps_wages = int(min(epf_wages, 15000))
        epf_contrib = int(r.get("employee_pf", 0))
        eps_contrib = int(r.get("employer_eps", 0) if r.get("employer_eps") else epf_wages * 8.33 / 100)
        epf_eps_diff = int(r.get("employer_pf", 0)) - eps_contrib
        ncp_days = int(r.get("days_in_month", 30)) - int(r.get("days_worked", 30))
        lines.append(f"{uan}|{epf_wages}|{eps_wages}|{epf_contrib}|{eps_contrib}|{epf_eps_diff}|{ncp_days}|0")
    return "\n".join(lines).encode("utf-8")
