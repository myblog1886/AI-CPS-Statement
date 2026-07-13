import pytest, json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db import get_session
from app.models import Base, User, Client, Run
from app.auth import hash_password
from app.routers.client import get_current_user as client_get_current_user


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
    app.dependency_overrides[client_get_current_user] = override_user
    with TestClient(app) as tc:
        yield tc, db, client_rec
    app.dependency_overrides.clear()
    db.close()


def test_approve_sets_status(setup):
    tc, db, client_rec = setup
    run = Run(
        client_id=client_rec.id, month=6, year=2025,
        payroll_json='[]', compliance_json='[]', status="draft"
    )
    db.add(run)
    db.commit()
    resp = tc.post(f"/client/approve/{run.id}", follow_redirects=False)
    assert resp.status_code in (302, 303)
    db.refresh(run)
    assert run.status == "approved"


def test_approve_blocked_by_fail_findings(setup):
    tc, db, client_rec = setup
    findings = [{"status": "fail", "act": "PF Act", "section": "4", "reason": "x"}]
    run = Run(
        client_id=client_rec.id, month=6, year=2025,
        payroll_json='[]', compliance_json=json.dumps(findings), status="draft"
    )
    db.add(run)
    db.commit()
    resp = tc.post(f"/client/approve/{run.id}", follow_redirects=False)
    assert resp.status_code == 400
