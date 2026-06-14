# Deployment Guide

## Why Render + Supabase (not Vercel)

- **Render** (render.com): Free tier supports Python/FastAPI with a persistent process. Zero config — just push with `render.yaml` already in the repo.
- **Supabase** (supabase.com): Free tier gives 500MB PostgreSQL, REST API. No credit card required.
- **NOT Vercel** because Vercel's Python support is serverless functions only — FastAPI in-memory sessions and streaming responses (SSE) don't work. Render runs a persistent process matching FastAPI's design.

## Step 1: Create Supabase Project

1. Go to supabase.com → New project
2. Copy the **Project URL** and **anon/public API key** from Settings → API
3. Run the SQL in `docs/supabase_schema.sql` in the Supabase SQL editor

## Step 2: Deploy to Render

1. Push this repo to GitHub
2. Go to render.com → New → Web Service → connect your repo
3. Render auto-detects `render.yaml` and sets Python environment
4. Add environment variables in Render dashboard:
   - `SUPABASE_URL` = your project URL
   - `SUPABASE_KEY` = your anon key
   - `SECRET_KEY`  = any random string (e.g. run `python3 -c "import secrets; print(secrets.token_hex(32))"`)
5. Click **Deploy** — Render installs `requirements.txt` and starts the server

## Step 3: Test locally

```bash
cp .env.example .env
# Fill in SUPABASE_URL and SUPABASE_KEY in .env
cd /Users/madhavibhat/payroll_v2
uvicorn app.main:app --reload --port 8002
# Open http://localhost:8002
```

## Updating statutory logic (PF/labor law changes)

Only ever edit `app/payroll_engine.py`. Key constants at the top of the file:

| Constant | Change when |
|---|---|
| `PF_WAGE_CEILING` | EPFO updates the ₹15,000 wage ceiling |
| `ESIC_GROSS_CEILING` | ESIC threshold changes from ₹21,000 |
| `_pt_maharashtra()` | State budget updates PT slabs |
| `EMPLOYEE_PF_RATE` etc. | Contribution rates change |

No other file needs to change when law changes. The engine is isolated in one module.

## Architecture overview

```
app/
├── main.py              # FastAPI app, route wiring only
├── payroll_engine.py    # ALL statutory logic — isolated, updateable
├── ecr_generator.py     # ECR 2.0 + ESIC CSV generation
├── pdf_generator.py     # Salary slip PDFs
├── db.py                # Supabase persistence (graceful fallback if unavailable)
└── routers/
    ├── payroll.py       # POST /process — single company
    ├── compare.py       # POST /compare — up to 5 companies vs New Boss
    └── history.py       # GET /history — audit log
```
