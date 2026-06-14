import os
import json
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

_client = None

def get_db():
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        if url and key:
            from supabase import create_client
            _client = create_client(url, key)
    return _client


def _result_to_dict(r) -> dict:
    if hasattr(r, '__dict__'):
        return {k: v for k, v in r.__dict__.items() if not k.startswith('_')}
    return dict(r)


def save_run(
    company_name: str,
    establishment_id: str,
    month: int,
    year: int,
    summary: dict,
    results: list,
    ecr_text: str,
    esic_csv: str,
) -> str:
    import uuid
    db = get_db()
    if not db:
        return str(uuid.uuid4())

    results_serializable = [_result_to_dict(r) for r in results]
    row = {
        "company_name": company_name,
        "establishment_id": establishment_id,
        "month": month,
        "year": year,
        "total_employees": summary["total_employees"],
        "total_gross": summary["total_gross"],
        "total_net": summary["total_net"],
        "total_pf_challan": summary["total_pf_challan"],
        "total_esic_challan": summary["total_esic_challan"],
        "results_json": json.dumps(results_serializable),
        "ecr_text": ecr_text,
        "esic_csv": esic_csv,
    }
    resp = db.table("payroll_runs").insert(row).execute()
    return resp.data[0]["id"]


def list_runs(limit: int = 50) -> list:
    db = get_db()
    if not db:
        return []
    resp = (
        db.table("payroll_runs")
        .select("id,company_name,establishment_id,month,year,total_employees,total_gross,total_net,total_pf_challan,total_esic_challan,created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return resp.data


def get_run(run_id: str) -> Optional[dict]:
    db = get_db()
    if not db:
        return None
    resp = db.table("payroll_runs").select("*").eq("id", run_id).execute()
    return resp.data[0] if resp.data else None
