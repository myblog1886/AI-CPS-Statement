import csv, io


def generate_esic(payroll_results: list[dict], month: int, year: int) -> bytes:
    """Generate ESIC monthly contribution CSV. Returns bytes."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["IP_NUMBER", "IP_NAME", "NO_OF_DAYS_WORKED", "TOTAL_WAGES",
                     "EMPLOYEE_CONTRIBUTION", "EMPLOYER_CONTRIBUTION"])
    for r in payroll_results:
        writer.writerow([
            r.get("esic_number", "") or "",
            r.get("name", ""),
            r.get("days_worked", 0),
            round(r.get("gross_salary", 0), 2),
            round(r.get("employee_esic", 0), 2),
            round(r.get("employer_esic", 0), 2),
        ])
    return buf.getvalue().encode("utf-8")
