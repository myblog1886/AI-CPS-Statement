# Payroll CRM

A local payroll compliance CRM for Indian statutory requirements (PF, ESIC, PT, LWF). Built as a CPS LLP internal tool using FastAPI and SQLite, with production-ready support for switching to Neon PostgreSQL.

## Prerequisites

- **Python 3.11+**
- The `payroll_v2` engine at `/Users/madhavibhat/payroll_v2`
- The `cps-compliance-platform` at `/Users/madhavibhat/cps-compliance-platform`
- An Anthropic API key (for unstructured file parsing and text edits)

## Setup

Clone the repository and install dependencies:

```bash
cd /Users/madhavibhat/payroll_crm
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file in the project root with the following configuration:

```
SECRET_KEY=your-secret-key-here
CLAUDE_API_KEY=sk-ant-...
DATABASE_URL=sqlite:///./payroll_crm.db   # default; override for Neon
```

## Seed the Database

Initialize the database with a default operator account:

```bash
python seed.py
```

This creates an admin operator account with credentials: `admin@cps.in` / `admin123`

## Run the Application

Start the FastAPI development server:

```bash
uvicorn app.main:app --reload
```

Then open [http://localhost:8000](http://localhost:8000) in your browser. You will be redirected to the login page.

## Default Credentials

| Email | Password | Role |
|-------|----------|------|
| admin@cps.in | admin123 | Operator |

## User Roles

### Operator (CPS Staff)
- View all clients
- Add new client companies
- View all payroll runs across clients
- Manage compliance reviews

### Client
- View only their own payroll runs
- Download approved outputs
- Access role assigned by operators through the panel

## Workflow

1. **Operator logs in** → Uses the admin panel to add a new client company
2. **Upload employee data** → Client or operator uploads a file (CSV, Excel, PDF, image)
3. **Automatic processing** → System runs payroll calculations and compliance checks
4. **Review screen** → Displays payroll summary and compliance findings
5. **Compliance validation** → If compliance findings include failures, they must be fixed before approval
6. **Approve run** → Once approved, 5 download files unlock:
   - EPFO ECR TXT (Employee Provident Fund submission)
   - ESIC CSV (Employee State Insurance submission)
   - Salary Slips ZIP (Individual employee salary documents)
   - Bank Transfer CSV (Payment instruction file)
   - Compliance Report PDF (Summary of compliance status)
7. **Edit and reprocess** → Can re-edit via text instructions or re-upload corrected files to create a new run version

## Supported File Formats

### Structured Formats
- **CSV** (Comma-Separated Values) — auto-detects columns
- **XLSX** (Excel 2007+) — auto-detects columns
- **XLS** (Excel 97-2003) — auto-detects columns

### Unstructured Formats
- **PDF** — parsed via Claude API
- **JPG** — parsed via Claude API
- **PNG** — parsed via Claude API

## Running Tests

Execute the test suite:

```bash
python -m pytest tests/ -v
```

Expected output: 27 tests passing.

## Production Switch to Neon PostgreSQL

To switch from SQLite to Neon PostgreSQL in production, update the `DATABASE_URL` in your `.env` file:

```
DATABASE_URL=postgresql://user:pass@host/db
```

No code changes are required — the application uses SQLAlchemy ORM which is database-agnostic.

## Project Structure

```
payroll_crm/
├── app/
│   ├── main.py          # FastAPI entry point
│   ├── db.py            # SQLAlchemy session and database configuration
│   ├── models.py        # SQLAlchemy ORM models
│   ├── auth.py          # Authentication and authorization helpers
│   ├── engines/         # Payroll and compliance engine wrappers
│   ├── ingest/          # Structured and unstructured file parsers
│   ├── output/          # ECR, ESIC, slips, bank transfer, and PDF generators
│   └── routers/         # FastAPI routers for API endpoints
├── templates/           # Jinja2 HTML templates
├── static/              # CSS stylesheets
├── tests/               # pytest test suite
├── seed.py              # Database initialization script
├── requirements.txt     # Python package dependencies
├── .env                 # Environment configuration (local development)
└── .env.example         # Template for .env
```

---

Built by CPS LLP. For questions or support, contact the development team.
