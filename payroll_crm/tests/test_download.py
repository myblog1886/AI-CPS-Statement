import pytest, json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db import get_session
from app.models import Base, User, Client, Run
from app.auth import hash_password
from app.routers.download import get_current_user as download_get_current_user
from app.output.ecr import generate_ecr
from app.output.esic import generate_esic
from app.output.slips import generate_slips_zip
from app.output.bank import generate_bank_csv

SAMPLE_PAYROLL = [{
    "name": "Rahul", "basic": 18000.0, "da": 0.0, "hra": 0.0,
    "other_allowances": 0.0, "gross_salary": 18000.0, "net_salary": 16200.0,
    "employee_pf": 2160.0, "employer_pf": 2160.0, "employer_eps": 1500.0,
    "employee_esic": 135.0, "employer_esic": 585.0, "pt": 200.0,
    "days_in_month": 30, "days_worked": 30,
    "uan": "100000000001", "esic_number": "12345", "bank_account": "1234567890",
    "ifsc_code": "SBIN0001234", "designation": "Engineer", "department": "Tech",
    "advance_deduction": 0.0,
}]


def test_generate_ecr_returns_bytes():
    result = generate_ecr(SAMPLE_PAYROLL, 6, 2025)
    assert isinstance(result, bytes)
    assert b"100000000001" in result


def test_generate_esic_returns_csv_bytes():
    result = generate_esic(SAMPLE_PAYROLL, 6, 2025)
    assert isinstance(result, bytes)
    assert b"Rahul" in result


def test_generate_slips_zip_returns_zip():
    result = generate_slips_zip(SAMPLE_PAYROLL, 6, 2025)
    assert isinstance(result, bytes)
    assert result[:2] == b"PK"  # ZIP magic bytes


def test_generate_bank_csv_returns_csv():
    result = generate_bank_csv(SAMPLE_PAYROLL, 6, 2025)
    assert isinstance(result, bytes)
    assert b"Rahul" in result


@pytest.fixture
def setup():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    user = User(email="op@test.com", password_hash=hash_password("pass"), role="operator")
    client_rec = Client(name="Acme", gstin="", state="MH", epf_registered=True, esic_registered=False)
    db.add_all([user, client_rec])
    db.commit()
    db.refresh(user)

    def override_session():
        try:
            yield db
        finally:
            pass

    def override_user():
        return user

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[download_get_current_user] = override_user
    with TestClient(app) as tc:
        yield tc, db, client_rec
    app.dependency_overrides.clear()
    db.close()


def test_download_requires_approved_run(setup):
    tc, db, client_rec = setup
    run = Run(
        client_id=client_rec.id, month=6, year=2025,
        payroll_json=json.dumps(SAMPLE_PAYROLL),
        compliance_json='[]', status="draft"
    )
    db.add(run)
    db.commit()
    resp = tc.get(f"/client/download/{run.id}/ecr", follow_redirects=False)
    assert resp.status_code == 403
