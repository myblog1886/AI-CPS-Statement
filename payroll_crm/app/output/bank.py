import csv, io


def generate_bank_csv(payroll_results: list[dict], month: int, year: int) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["EMPLOYEE_NAME", "BANK_ACCOUNT", "IFSC_CODE", "NET_SALARY", "REMARKS"])
    for r in payroll_results:
        writer.writerow([
            r.get("name", ""),
            r.get("bank_account", "") or "",
            r.get("ifsc_code", "") or "",
            round(r.get("net_salary", 0), 2),
            f"Salary {month:02d}/{year}",
        ])
    return buf.getvalue().encode("utf-8")
