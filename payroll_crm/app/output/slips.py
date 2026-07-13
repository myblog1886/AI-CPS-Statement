import io, zipfile

SLIP_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Salary Slip</title>
<style>body{{font-family:Arial,sans-serif;margin:40px}}
table{{width:100%;border-collapse:collapse}}td{{padding:6px;border:1px solid #ccc}}</style>
</head><body>
<h2>Salary Slip — {month:02d}/{year}</h2>
<p><strong>Name:</strong> {name} | <strong>Designation:</strong> {designation}</p>
<table>
<tr><td>Basic</td><td>₹{basic:.2f}</td><td>Employee PF</td><td>₹{employee_pf:.2f}</td></tr>
<tr><td>DA</td><td>₹{da:.2f}</td><td>ESIC</td><td>₹{employee_esic:.2f}</td></tr>
<tr><td>HRA</td><td>₹{hra:.2f}</td><td>PT</td><td>₹{pt:.2f}</td></tr>
<tr><td>Other Allow.</td><td>₹{other_allowances:.2f}</td><td>Advance Deduction</td><td>₹{advance_deduction:.2f}</td></tr>
<tr><td><strong>Gross</strong></td><td>₹{gross_salary:.2f}</td><td><strong>Net</strong></td><td>₹{net_salary:.2f}</td></tr>
</table>
</body></html>"""


def generate_slips_zip(payroll_results: list[dict], month: int, year: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in payroll_results:
            name_safe = r.get("name", "emp").replace(" ", "_")
            html = SLIP_TEMPLATE.format(
                month=month, year=year,
                name=r.get("name", ""),
                designation=r.get("designation", ""),
                basic=r.get("basic", 0),
                da=r.get("da", 0),
                hra=r.get("hra", 0),
                other_allowances=r.get("other_allowances", 0),
                employee_pf=r.get("employee_pf", 0),
                employee_esic=r.get("employee_esic", 0),
                pt=r.get("pt", 0),
                advance_deduction=r.get("advance_deduction", 0),
                gross_salary=r.get("gross_salary", 0),
                net_salary=r.get("net_salary", 0),
            )
            zf.writestr(f"{name_safe}_slip.html", html)
    return buf.getvalue()
