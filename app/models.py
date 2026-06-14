from pydantic import BaseModel

class RunSummary(BaseModel):
    run_id: str
    company_name: str
    month: int
    year: int
    total_employees: int
    total_gross: float
    total_net: float
    total_pf_challan: float
    total_esic_challan: float
    created_at: str
