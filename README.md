# CPS LLP — India Payroll Copilot

An AI-assisted payroll processing tool built for India statutory compliance. Upload a company's monthly salary data and instantly generate:

- **ECR TXT file** ready to upload to the EPFO portal
- **ESIC contribution CSV** for monthly filing
- **Individual salary slip PDFs** (and a ZIP of all slips)
- **Payroll register CSV** for your records
- **Bank payment advice file** for salary disbursement

Statutory calculations covered: **PF (EPF + EPS + EDLI), ESIC, Professional Tax (Maharashtra), LWF (Maharashtra)**

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Installation](#2-installation)
3. [Running the App](#3-running-the-app)
4. [Preparing Your Salary Input File](#4-preparing-your-salary-input-file)
5. [Single Company Payroll — Step by Step](#5-single-company-payroll--step-by-step)
6. [5-Company Batch Processing — Step by Step](#6-5-company-batch-processing--step-by-step)
7. [Understanding the Outputs](#7-understanding-the-outputs)
8. [Validating Against New Boss](#8-validating-against-new-boss)
9. [Statutory Rules Applied](#9-statutory-rules-applied)
10. [Column Reference for Input Files](#10-column-reference-for-input-files)
11. [Sample Test Files](#11-sample-test-files)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Prerequisites

Before you begin, make sure the following are installed on your machine:

- **Python 3.9 or higher**
  Check by running: `python3 --version`
  Download from: https://www.python.org/downloads/

- **pip** (comes with Python)
  Check by running: `pip3 --version`

- **Git** (to clone the repository)
  Check by running: `git --version`

> **Windows users:** All commands below work in PowerShell or Command Prompt. Replace `python3` with `python` and `pip3` with `pip`.

---

## 2. Installation

### Step 1 — Clone the repository

Open your Terminal (Mac/Linux) or Command Prompt (Windows) and run:

```bash
git clone https://github.com/myblog1886/AI-CPS-Statement.git
cd AI-CPS-Statement
```

### Step 2 — Install Python dependencies

```bash
pip3 install -r requirements.txt
```

This installs FastAPI, pandas, reportlab (for PDFs), and all other required libraries. It takes about 1–2 minutes the first time.

If you see a permissions error on Mac, try:
```bash
pip3 install -r requirements.txt --user
```

### Step 3 — Verify the installation

```bash
python3 -c "import fastapi, pandas, reportlab; print('All good — ready to run!')"
```

You should see: `All good — ready to run!`

---

## 3. Running the App

### Start the server

```bash
uvicorn app.main:app --reload --port 8002
```

You should see output like:
```
INFO:     Uvicorn running on http://127.0.0.1:8002 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Application startup complete.
```

### Open the app

Open your browser and go to: **http://localhost:8002**

You will see the CPS LLP Payroll Copilot home page with two tabs in the navigation:
- **Single Company** — process one company at a time
- **5-Company Compare** — process up to 5 companies simultaneously

> **To stop the server:** Press `Ctrl + C` in the terminal.

> **To restart after a reboot**, just run the `uvicorn` command again from the `AI-CPS-Statement` folder.

---

## 4. Preparing Your Salary Input File

The tool accepts **CSV (.csv) or Excel (.xlsx)** files. The file should have one row per employee.

### Required columns

| Column Name | Description | Example |
|---|---|---|
| `emp_id` | Employee ID or serial number | E001, 1, EMP-001 |
| `name` | Employee full name | Rahul Sharma |
| `basic` | Basic salary (monthly, full month) | 15000 |
| `da` | Dearness allowance | 3000 |
| `hra` | House rent allowance | 6000 |
| `other_allowances` | Special / conveyance / other pay | 2000 |
| `days_in_month` | Total calendar/working days in the month | 31 |
| `days_worked` | Actual days the employee worked | 28 |

### Optional but recommended columns

| Column Name | Description |
|---|---|
| `uan` | UAN number — required for ECR file upload to EPFO |
| `pf_number` | PF member number |
| `esic_number` | ESIC IP number |
| `designation` | Job title (appears on salary slip) |
| `department` | Department name (appears on salary slip) |
| `bank_account` | Bank account number (for bank payment file) |
| `ifsc_code` | Bank IFSC code |
| `advance_deduction` | Any advance or loan recovery amount |

### Important notes on the input file

- **Column names are flexible** — the tool recognises common variations. For example, `basic_salary`, `basic_pay`, and `basic` all map to the basic salary column. See the full alias list in [Section 10](#10-column-reference-for-input-files).
- **Salary figures should be the full-month amounts**, not prorated. The tool prorates automatically based on days_worked ÷ days_in_month.
- **Do not include totals rows** at the bottom — the tool will automatically skip rows where the emp_id is blank or says "Total".
- **Days in month varies by industry** — factories often use 26, offices use 30 or 31. Enter the actual number your company uses.
- If you only have a gross salary column (no split into basic/HRA/etc.), name it `gross` and the tool will split it automatically as 50% basic, 30% HRA, 20% other.

### Downloading a sample file

From the app home page, click **"Download sample CSV"** to get a pre-filled example with 6 employees showing all supported columns.

---

## 5. Single Company Payroll — Step by Step

Use this tab to process one company's monthly payroll completely.

### Step 1 — Open the home page

Go to **http://localhost:8002** — you will see the upload form.

### Step 2 — Fill in company details

| Field | What to enter |
|---|---|
| **Company Name** | The legal name of the company (appears on salary slips and ECR file) |
| **Establishment ID** | The company's EPFO establishment code (format: MH/MUM/12345). If unknown, enter a placeholder — you can update it before uploading to EPFO. |
| **Month** | The payroll month (e.g., select "February" for Feb 2026 payroll) |
| **Year** | The payroll year (e.g., 2026) |

### Step 3 — Upload the salary file

Click **"Choose File"** and select your salary CSV or Excel file. The tool accepts `.csv` and `.xlsx` formats.

### Step 4 — Click "Run Payroll"

The button will show a loading spinner while processing. For 50 employees this takes about 2–3 seconds.

### Step 5 — Review the results page

You will see:

**Summary stats at the top:**
- Total Gross Salary
- Total Net Pay
- PF Challan amount (what you need to pay EPFO)
- ESIC Challan amount (what you need to pay ESIC)

**Statutory summary table:**
A breakdown of employee PF, employer EPF, employer EPS, employee ESIC, employer ESIC, and professional tax — both individual and total.

**Employee detail table:**
One row per employee showing days worked, gross earned, all deductions, and net pay. Each row has a **PDF** button to download that employee's individual salary slip.

### Step 6 — Download the outputs

Click each button to download:

| Button | What you get | What it's used for |
|---|---|---|
| **ECR TXT (EPFO)** | `.txt` file in ECR 2.0 format | Upload directly to the EPFO Unified Portal to file the monthly return |
| **ESIC CSV** | `.csv` with IP numbers and contributions | For ESIC monthly contribution filing |
| **Payroll Register** | Full CSV with all statutory figures per employee | Internal record-keeping and audit |
| **Bank Payment File** | CSV with account number, IFSC, and net pay per employee | Share with your bank for bulk salary transfers |
| **All Salary Slips (ZIP)** | ZIP file containing one PDF per employee | Distribute to employees |

### Step 7 — Upload ECR to EPFO portal

1. Log into the EPFO Unified Portal (unifiedportal-emp.epfindia.gov.in)
2. Go to **Payment → ECR Upload**
3. Upload the downloaded `.txt` file
4. Verify the member-wise contribution summary
5. Approve and generate the TRRN challan
6. Share the challan PDF with the employer for payment

---

## 6. Five-Company Batch Processing — Step by Step

Use this tab when you are processing payroll for multiple client companies in the same month. Instead of going through the single company tab five times, you can upload all of them together and get all outputs in one session.

### Step 1 — Go to the Compare page

Click **"5-Company Compare"** in the top navigation, or go to **http://localhost:8002/compare**

### Step 2 — Select the month and year

At the top of the form, choose the payroll month and year. This applies to all companies you upload.

### Step 3 — Fill in company slots

The form has 5 company slots. For each company you want to process:

1. Enter the **Company Name** (e.g., "ABC Manufacturing Pvt Ltd")
2. Upload the **Salary File** (.csv or .xlsx) — same format as the single company tab
3. Optionally upload a **New Boss ECR .txt** file if you want to validate our numbers against New Boss (see [Section 8](#8-validating-against-new-boss))

You do not need to fill all 5 slots — leave unused slots blank and the tool skips them.

### Step 4 — Click "Run Comparison"

The tool processes all uploaded companies simultaneously. You will see a loading spinner.

### Step 5 — Review the Company Scorecard

At the top of the results page is a summary table showing all companies side by side:

| Column | Meaning |
|---|---|
| Company | Company name |
| Employees | Number of employees processed |
| Our Gross | Total gross salary computed by our tool |
| Our PF Challan | Total PF amount payable |
| Our ESIC | Total ESIC amount payable |
| NB Matched / Diverged | (Only shown if New Boss file was uploaded) How many employees match or differ |

### Step 6 — Download outputs per company

Below the scorecard, each company has its own card with a **full set of download buttons** — ECR TXT, ESIC CSV, Payroll Register, Bank File, and Salary Slips ZIP. These work exactly the same as the single company tab.

---

## 7. Understanding the Outputs

### ECR TXT file

This is the Electronic Challan-cum-Return file in EPFO's ECR 2.0 format. Each line represents one employee:

```
UAN#MemberName#GrossWages#EPFWages#EPSWages#NCPDays#RefundOfAdvances#EPFContri#EPSContri#EPFEPSDiff#NCP#...
```

- **Gross Wages** = total earned salary for the month (prorated if days_worked < days_in_month)
- **EPF Wages** = min(Basic + DA, ₹15,000) — the wage on which PF is calculated
- **NCP Days** = Non-Contributing Period days = days_in_month − days_worked

### Salary Slip PDF

Each employee's slip shows:
- Company name and month/year
- Employee name, ID, designation, department
- Earnings breakdown: Basic, DA, HRA, Other Allowances, Gross Earned
- Deductions: Employee PF, ESIC, Professional Tax, LWF, Advance
- Net Pay

### Payroll Register CSV

A full audit-ready CSV with every statutory figure per employee. Useful for your own records and for reconciling with the challan.

### Bank Payment File

A CSV formatted for bulk upload to most Indian bank portals (HDFC, ICICI, SBI, Axis, etc.) with account number, IFSC, net amount, and a payment reference.

---

## 8. Validating Against New Boss

If you currently use New Boss to generate ECR files, you can use this tool to cross-check the numbers before switching over. Here's how:

### Step 1 — Generate the ECR file from New Boss as usual

In New Boss: PF section → E-Return → E-Challan Ver.2 → Select E-Returns → save the `.txt` file.

### Step 2 — Upload both files in the 5-Company Compare tab

In a company slot:
- Upload the **salary CSV** in the "Salary File" field
- Upload the **New Boss ECR .txt** in the "New Boss ECR .txt" field

### Step 3 — Review the comparison table

For each employee, you will see columns for both our value and the New Boss value for:
- Gross Wages
- EPF Wages
- Employee PF
- Employer EPF
- Employer EPS
- NCP Days

**Colour coding:**
- Values that match are shown normally
- Values that differ by more than ₹1 are highlighted in **red** with bold text
- The last column shows ✓ Match or ✗ Diverge per employee

### Step 4 — Investigate divergences

Common reasons for differences between our tool and New Boss:
- **Rounding** — New Boss may round differently. Differences of ₹1–2 are usually rounding and can be ignored.
- **Days in month** — New Boss may use a different calendar days setting (26 vs 30 vs 31). Check what your New Boss configuration uses and match it in your input file.
- **PF on full basic vs capped** — New Boss may be configured to compute PF on the full basic (not capped at ₹15,000) for certain employees. Our tool caps at ₹15,000 per EPFO rules.
- **Arrears or adjustments** — If New Boss has manual adjustments for a previous month, those won't appear in our calculation from the current month's salary file.

---

## 9. Statutory Rules Applied

All calculations follow current Indian statutory requirements for Maharashtra:

### Provident Fund (PF)

| Component | Rate | Wage Ceiling |
|---|---|---|
| Employee PF | 12% of (Basic + DA) | Capped at ₹15,000 wage |
| Employer EPF | 3.67% of (Basic + DA) | Capped at ₹15,000 wage |
| Employer EPS | 8.33% of (Basic + DA) | Max ₹1,250/month |

Employees with (Basic + DA) above ₹15,000 contribute 12% on ₹15,000 = ₹1,800 max employee PF.

### ESIC (Employee State Insurance)

| Gross Salary | Applicability |
|---|---|
| ≤ ₹21,000/month | ESIC applicable |
| > ₹21,000/month | ESIC not applicable |

| Component | Rate |
|---|---|
| Employee ESIC | 0.75% of gross earned |
| Employer ESIC | 3.25% of gross earned |

### Professional Tax (Maharashtra)

| Gross Salary | PT Amount |
|---|---|
| Up to ₹7,500 | Nil |
| ₹7,501 – ₹10,000 | ₹175/month |
| Above ₹10,000 | ₹200/month (₹300 in February) |

### Labour Welfare Fund (Maharashtra)

Deducted only in **June** and **December**:
- Employee: ₹6 per half-year
- Employer: ₹12 per half-year

### Proration

All salary components are prorated:
```
Earned Amount = Full Month Amount × (Days Worked ÷ Days in Month)
```

---

## 10. Column Reference for Input Files

The tool recognises these column name variations automatically. You do not need to rename your columns as long as they match one of these:

| Field | Accepted column names |
|---|---|
| Employee ID | emp_id, employee_id, empid, id, sr_no, sl_no, emp_code, employee_code, sno |
| Name | name, employee_name, emp_name, full_name, employee, staff_name |
| UAN | uan, uan_number, uan_no |
| PF Number | pf_number, pf_no, pf_account, epf_number |
| ESIC Number | esic_number, esic_no, ip_number, esic_ip |
| Basic | basic, basic_salary, basic_pay, basic_wages, basic_ctc, base_salary, bs |
| DA | da, dearness_allowance, dearness_allow, da_amount |
| HRA | hra, house_rent_allowance, house_rent, hra_amount |
| Other Allowances | other_allowances, other, special_allowance, conveyance, ot_rs, ot_amount, overtime_amount |
| Days in Month | days_in_month, total_days, working_days_in_month, calendar_days, month_days |
| Days Worked | days_worked, days_present, present_days, actual_days, paid_days, working_days |
| Advance | advance_deduction, advance, loan_deduction, loan, recovery |
| Bank Account | bank_account, account_number, bank_acc, acc_no, account_no |
| IFSC | ifsc_code, ifsc, bank_ifsc, bank_code |
| Designation | designation, role, position, job_title, title, grade |
| Department | department, dept, division, section, cost_centre, team |

---

## 11. Sample Test Files

The `test_data/` folder contains ready-to-use sample files:

| File | Company | Industry | Employees | Notes |
|---|---|---|---|---|
| `company_single_techspark.csv` | TechSpark Solutions | IT | 10 | Good for Single Company tab testing. Mix of high-salary (no ESIC) and regular employees. One employee with partial attendance. |
| `company1_brightmfg.csv` | Bright Manufacturing | Factory | 12 | Uses 26 days-in-month (factory norm). All employees ESIC-eligible. |
| `company2_starpharma.csv` | Star Pharma | Pharma | 10 | Mix of senior (no ESIC) and junior staff. One advance deduction. |
| `company3_nexusretail.csv` | Nexus Retail | Retail | 12 | Retail company with varied designations. One employee with partial attendance. |
| `company4_alphalogistics.csv` | Alpha Logistics | Logistics | 10 | Uses 30 days-in-month. Mix of drivers, supervisors, office staff. |
| `company5_sunriseedu.csv` | Sunrise Education | School | 11 | Uses 25 days-in-month (school norm). Principal above ESIC ceiling. |

### Using your own actual salary data

When using real company salary data:

1. Export the salary sheet from whatever system you use (Tally, Excel, HR software) as a CSV or Excel file.
2. Check that the column names match those listed in Section 10. Rename if needed.
3. Make sure salary figures are **full-month amounts** (not already prorated).
4. Enter the correct **days_in_month** for that company (factories: 26, offices: 30 or 31, schools: 25 are common).
5. Enter **days_worked** as the actual attendance for each employee.
6. If some employees don't have UAN numbers yet, leave that column blank — the ECR line will still be generated but the UAN field will be empty (you will need to add UANs before uploading to EPFO).

---

## 12. Troubleshooting

### "No valid employee rows found"
The tool could not find employee data in your file. Check:
- Does your file have a header row with column names?
- Is the emp_id column present? Rows without a numeric or alphanumeric emp_id are skipped.
- Open the file in Excel — is there data starting from row 2?

### "Could not extract salary data"
Rows were found but salary columns could not be identified. Check:
- Do you have at least one of: `basic`, `hra`, `gross`, or `ctc` column?
- Are the salary values numeric (no ₹ symbol or commas in the cells)?

### Salary slip shows ₹0 gross
This usually means the proration calculation resulted in zero because `days_worked` is 0. Check your attendance column.

### ESIC shows "N/A" for all employees
This is correct — if all employees have gross salary above ₹21,000, none are ESIC-eligible.

### ECR file shows empty UAN fields
You did not include a `uan` column in your input file. The ECR file is generated but EPFO will reject it without valid UANs. Add the UAN column to your salary file.

### Server won't start — "address already in use"
Another process is using port 8002. Either stop that process or use a different port:
```bash
uvicorn app.main:app --reload --port 8003
```
Then open http://localhost:8003

### Downloads return "Session expired"
Sessions are stored in memory. If you restarted the server after running payroll, the session is gone. Re-upload the file and run payroll again — downloads will work immediately after.

---

## Updating for New PF / Labor Law Changes

When EPFO or the government updates statutory rates or ceilings, only **one file** needs to change:

`app/payroll_engine.py` — the constants at the top of the file:

```python
PF_WAGE_CEILING      = 15_000   # Change if EPFO raises the wage ceiling
ESIC_GROSS_CEILING   = 21_000   # Change if ESIC threshold changes
EMPLOYEE_PF_RATE     = 0.12     # 12% employee PF
EMPLOYER_EPF_RATE    = 0.0367   # 3.67% employer EPF
EMPLOYER_EPS_RATE    = 0.0833   # 8.33% employer EPS
EMPLOYEE_ESIC_RATE   = 0.0075   # 0.75% employee ESIC
EMPLOYER_ESIC_RATE   = 0.0325   # 3.25% employer ESIC
```

No other file needs to be touched. This isolation is intentional — the rest of the app (UI, downloads, comparisons) is completely unaffected by statutory updates.

---

## Tech Stack

- **Backend:** Python 3.9 + FastAPI
- **PDF generation:** ReportLab
- **Data processing:** Pandas
- **Templates:** Jinja2
- **Database (optional):** Supabase (PostgreSQL) — for persisting run history
- **Deployment:** Render.com (see `docs/DEPLOYMENT.md`)
