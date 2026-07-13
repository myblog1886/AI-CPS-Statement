# Payroll CRM — End-to-End Local Application Design

**Date:** 2026-07-04  
**Author:** Forward Deployment Engineer (Claude)  
**Status:** Approved for implementation  
**Working directory:** `/Users/madhavibhat/payroll_crm/`

---

## 1. Purpose

Build a local-first, end-to-end payroll compliance application for CPS LLP that:

1. Ingests client attendance and salary files in any format (structured or unstructured)
2. Runs payroll calculations (PF, ESIC, PT, LWF) via the existing payroll_v2 engine
3. Validates the payroll output through the existing CPS compliance platform (15-act rule engine) **before** any files are generated
4. Presents a unified review screen to both the CPS operator and the client
5. Supports an iterative edit loop (re-upload corrected file OR type a natural language instruction)
6. Unlocks final output files only after compliance validation passes and client approves
7. Delivers: EPFO ECR TXT, ESIC CSV, salary slips ZIP, bank transfer file, compliance report PDF

The local version uses SQLite and runs on `uvicorn` with no paid services. A single environment variable swap migrates the database to Neon (PostgreSQL) or local Postgres for production.

---

## 2. Scope

### In scope
- New `payroll_crm/` FastAPI application
- Two roles: `operator` (CPS staff, sees all clients) and `client` (sees own runs only)
- File ingestion: CSV/Excel via pandas, unstructured (PDF, image, Word) via Claude API
- Payroll engine integration (imported from `payroll_v2/app/`)
- Compliance engine integration (imported from `cps-compliance-platform/rules/`)
- Compliance as a validation gate — blocking issues prevent file generation
- Iterative review loop with full version history
- 7 UI screens (Jinja2 templates)
- SQLite locally; DATABASE_URL env var enables Postgres/Neon with zero code changes
- All output files served via download buttons in the browser

### Out of scope (Phase 2)
- WhatsApp integration
- Biometric / HRMS API ingestion
- Email delivery of output files
- Multi-company batch comparison (already exists in payroll_v2 as a separate tab)
- Cloud deployment (Fly.io, Neon, Cloudflare R2)

---

## 3. Architecture

### Approach: Single FastAPI process, engines as Python libraries

`payroll_crm/` is a new FastAPI app. Both existing engines are imported directly as Python modules — no HTTP calls between processes. One `uvicorn` process handles everything.

```
/Users/madhavibhat/
├── payroll_v2/              ← existing, untouched
├── cps-compliance-platform/ ← existing, untouched
└── payroll_crm/             ← new application
    ├── app/
    │   ├── engines/
    │   │   ├── payroll.py       ← imports payroll_v2 engine + generators
    │   │   └── compliance.py    ← imports cps-compliance-platform rules
    │   ├── routers/
    │   │   ├── auth.py          ← login, logout, session, role guard decorator
    │   │   ├── operator.py      ← client CRUD, all-client dashboard
    │   │   ├── client.py        ← upload, review, edit, approve
    │   │   ├── run.py           ← orchestrator: ingest → payroll → compliance → version
    │   │   └── download.py      ← serve ECR, ESIC, slips, bank file, compliance PDF
    │   ├── ingest/
    │   │   ├── structured.py    ← pandas parser (CSV, Excel)
    │   │   └── unstructured.py  ← Claude API parser (PDF, image, Word, etc.)
    │   ├── models.py            ← SQLAlchemy ORM models
    │   ├── db.py                ← engine + session factory from DATABASE_URL
    │   └── main.py              ← FastAPI app, router registration, static files
    ├── templates/               ← Jinja2 HTML templates (7 screens)
    ├── static/                  ← CSS, JS
    ├── outputs/                 ← generated files stored here (gitignored)
    ├── uploads/                 ← raw uploaded files (gitignored)
    ├── requirements.txt
    └── .env                     ← DATABASE_URL, CLAUDE_API_KEY, SECRET_KEY
```

### Python path setup

`payroll_v2/` and `cps-compliance-platform/` are added to `sys.path` at startup so their modules can be imported without installation:

```python
# app/main.py
import sys
sys.path.insert(0, "/Users/madhavibhat/payroll_v2")
sys.path.insert(0, "/Users/madhavibhat/cps-compliance-platform")
```

---

## 4. Database Schema

SQLite locally. One env var (`DATABASE_URL`) switches to PostgreSQL for production.

```sql
-- Users (created by operator; no self-registration)
CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role        TEXT NOT NULL CHECK(role IN ('operator','client')),
    client_id   INTEGER REFERENCES clients(id),  -- NULL for operators
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Client companies managed by CPS
CREATE TABLE clients (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    establishment_id TEXT,          -- e.g. MH/MUM/55001
    state            TEXT NOT NULL, -- e.g. Maharashtra
    industry_type    TEXT,          -- e.g. IT, Manufacturing, Education
    headcount        INTEGER,
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- One run = one month's payroll for one client
CREATE TABLE runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id   INTEGER NOT NULL REFERENCES clients(id),
    month       INTEGER NOT NULL,
    year        INTEGER NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    status      TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved')),
    created_by  INTEGER REFERENCES users(id),
    approved_by INTEGER REFERENCES users(id),
    approved_at DATETIME,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Raw uploaded files linked to a run
CREATE TABLE run_files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL REFERENCES runs(id),
    file_type    TEXT,    -- 'structured' or 'unstructured'
    original_name TEXT,
    storage_path TEXT NOT NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Edit requests (either text instruction or re-upload trigger)
CREATE TABLE edit_requests (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER NOT NULL REFERENCES runs(id),
    type       TEXT NOT NULL CHECK(type IN ('text','reupload')),
    content    TEXT,   -- natural language instruction for type='text'
    created_by INTEGER REFERENCES users(id),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Generated output files linked to a run version
CREATE TABLE outputs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL REFERENCES runs(id),
    output_type  TEXT NOT NULL CHECK(output_type IN ('ecr','esic','slips','bank','compliance')),
    storage_path TEXT NOT NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 5. File Ingestion

### Structured path (CSV, Excel)
Uses pandas with the column alias matching already in `payroll_v2`. Produces a list of employee dicts in the standard internal format.

### Unstructured path (PDF, image, Word, etc.)
Calls Claude API (Haiku 4.5 — cheapest). Prompt:

```
Extract payroll data from this document. Return a JSON array where each element is:
{
  "name": string,
  "emp_id": string or null,
  "basic": number,
  "da": number,
  "hra": number,
  "other_allowances": number,
  "days_in_month": number,
  "days_worked": number,
  "advance_deduction": number,
  "bank_account": string or null,
  "ifsc_code": string or null,
  "uan": string or null,
  "esic_number": string or null
}
Return only the JSON array, no explanation.
```

Both paths produce the same internal employee list format. All downstream logic is format-agnostic.

---

## 6. Orchestration Flow

```
POST /run/create  (upload + month + year)
        │
        ▼
  Ingest file (structured or unstructured path)
        │
        ▼
  Payroll Engine
  payroll_v2/app/payroll_engine.py
  → per-employee: PF, ESIC, PT, LWF, gross, net
  → summary: totals, ECR data, ESIC data
        │
        ▼
  Compliance Engine
  cps-compliance-platform/rules/central_acts.py
  cps-compliance-platform/rules/state_acts.py
  → validates payroll output + client profile
  → findings: list of {act, status, reason, priority, penalty}
        │
        ▼
  Save to DB: runs row (version N, status=draft)
  Store payroll_results + compliance_findings as JSON in run record
        │
        ▼
  Redirect to /review/{run_id}
```

**Edit loop:**

```
POST /run/{run_id}/edit
        │
        ├── type=reupload → re-ingest new file → create runs row (version N+1)
        └── type=text     → Claude API interprets instruction
                            → patches employee JSON
                            → re-runs both engines
                            → create runs row (version N+1)
        │
        ▼
  Redirect to /review/{run_id}  (now showing version N+1)
```

**Approval:**

```
POST /run/{run_id}/approve  (only if no RED compliance findings)
        │
        ▼
  Generate all output files:
    ECR TXT  → payroll_v2/app/ecr_generator.py
    ESIC CSV → payroll_v2/app/ecr_generator.py (generate_esic_csv)
    Slips ZIP → payroll_v2/app/pdf_generator.py (all employees)
    Bank file → CSV of account/IFSC/net pay
    Compliance PDF → ReportLab summary of all findings
        │
        ▼
  Write to outputs/ directory
  Insert rows into outputs table
  Update runs.status = 'approved', runs.approved_by, runs.approved_at
        │
        ▼
  Redirect to /download/{run_id}
```

---

## 7. Compliance Validation Gate

Findings from the compliance engine have three severity levels:

| Level | Colour | Effect |
|-------|--------|--------|
| `fail` | 🔴 Red | Blocks approval. Must fix (edit + re-run) |
| `partial` | 🟡 Amber | Warning. Client must check "Acknowledge and proceed" |
| `pass` | 🟢 Green | No action needed |

Approve button is disabled until:
- Zero `fail` findings, AND
- All `partial` findings have been acknowledged

---

## 8. UI Screens

All screens share a base Jinja2 template with role-aware navigation.

| # | Route | Role | Description |
|---|-------|------|-------------|
| 1 | `/login` | Both | Email + password. Redirects by role |
| 2 | `/operator/dashboard` | Operator | All clients, latest run status, new run button |
| 3 | `/operator/clients` | Operator | Create/edit clients, create client logins |
| 4 | `/upload` | Both | Drag-drop file, month/year selector, AI parse indicator |
| 5 | `/review/{run_id}` | Both | Split panel: payroll summary + compliance gate + edit bar |
| 6 | `/download/{run_id}` | Both | 5 download buttons, unlocked post-approval |
| 7 | `/history` | Both | Run list (operator: all; client: own). Click → read-only review |

### Review screen layout (Screen 5 — most critical)

```
┌─────────────────────────────┬──────────────────────────────────┐
│  PAYROLL SUMMARY  v2  draft │  COMPLIANCE VALIDATION            │
│                             │                                    │
│  Total Gross    ₹4,23,500   │  🟢 EPF & PF           PASS       │
│  Total PF        ₹50,820   │  🟢 ESIC               PASS       │
│  Total ESIC       ₹3,177   │  🟡 Minimum Wages    WARNING       │
│  Total Net      ₹3,69,503  │     "Suresh Patil ₹14k < MW"      │
│  Employees           10    │     [x] Acknowledge                │
│                             │  🔴 PT Filing         BLOCKED      │
│  [employee table]           │     "PT not registered in MH"     │
│                             │     Must fix before approving      │
└─────────────────────────────┴──────────────────────────────────┘
│  [↩ Re-upload corrected file]   [✏ Type an edit instruction]   │
│  [✓ Approve & Generate Files — LOCKED until red issues fixed]  │
└────────────────────────────────────────────────────────────────┘
```

---

## 9. Authentication

- Session-based auth using `itsdangerous` signed cookies (no OAuth, no JWT)
- `SECRET_KEY` in `.env`
- `role_required(role)` decorator on all routes
- Operator can impersonate / view any client run
- No self-registration — operator creates all accounts via `/operator/clients`
- Passwords hashed with `bcrypt`

---

## 10. Technology Stack

| Component | Local | Production swap |
|-----------|-------|-----------------|
| Web framework | FastAPI + uvicorn | Same |
| Templates | Jinja2 | Same |
| Database | SQLite via SQLAlchemy | `DATABASE_URL=postgresql://...` → Neon or local Postgres |
| Auth | itsdangerous sessions + bcrypt | Same |
| Structured ingestion | pandas + openpyxl | Same |
| Unstructured ingestion | Claude API (Haiku 4.5) | Same |
| Payroll engine | payroll_v2 (imported) | Same |
| Compliance engine | cps-compliance-platform (imported) | Same |
| ECR / ESIC generation | payroll_v2/app/ecr_generator.py | Same |
| PDF generation | ReportLab | Same |
| File storage | Local `outputs/` + `uploads/` dirs | Cloudflare R2 |
| Environment config | `.env` + python-dotenv | Same |

---

## 11. Error Handling

- Ingestion failure (Claude API timeout, unreadable PDF) → flash error on upload screen, file not saved, run not created
- Payroll engine exception → run saved with `status='error'`, error message shown on review screen
- Compliance engine exception per-act → that act shows as `partial` with "could not evaluate" reason (matches existing behaviour in cps-compliance-platform)
- Download of non-existent output → 404 with friendly message
- Unauthorised access (client trying to view another client's run) → redirect to own dashboard

---

## 12. Migration Path to Production

1. Set `DATABASE_URL=postgresql://...` in `.env` → SQLAlchemy auto-switches, run `alembic upgrade head`
2. Replace local `outputs/` path with Cloudflare R2 signed URLs in `download.py`
3. Deploy to Fly.io with `fly deploy` (same `uvicorn` start command)
4. Point existing domain DNS to Fly.io → Cloudflare handles SSL
5. No code changes to any engine, router, or template

---

## 13. Out of Scope Decisions

- **No Alembic migrations in Phase 1** — SQLAlchemy `create_all()` on startup for local dev. Alembic added before production.
- **No file size limits in Phase 1** — local only, single user.
- **No rate limiting** — local only.
- **No async ingestion queue** — sequential engine calls are under 5s for typical payroll files. `asyncio.gather()` added in production if needed.
