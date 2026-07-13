import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db import get_session
from app.models import Base, User, Client
from app.auth import hash_password
from app.routers.operator import require_operator


@pytest.fixture
def client_with_operator():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    # Create operator user — model uses password_hash
    user = User(email="op@test.com", password_hash=hash_password("pass"), role="operator")
    db.add(user)
    db.commit()
    db.refresh(user)

    def override_session():
        try:
            yield db
        finally:
            pass

    def override_operator():
        return user

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_operator] = override_operator
    with TestClient(app) as tc:
        yield tc, db, user
    app.dependency_overrides.clear()
    db.close()


def test_dashboard_requires_operator(client_with_operator):
    tc, db, user = client_with_operator
    # Remove the operator override to test auth enforcement
    saved = app.dependency_overrides.pop(require_operator)
    try:
        resp = tc.get("/operator/dashboard", follow_redirects=False)
        assert resp.status_code in (302, 303, 307)
    finally:
        app.dependency_overrides[require_operator] = saved


def test_add_client_creates_record(client_with_operator):
    tc, db, user = client_with_operator
    resp = tc.post("/operator/clients/add", data={
        "name": "Test Corp",
        "gstin": "27XXXXX",
        "state": "MH",
        "epf_registered": "true",
        "esic_registered": "false",
    }, follow_redirects=False)
    assert resp.status_code in (302, 303)
    db.expire_all()
    client_record = db.query(Client).filter_by(name="Test Corp").first()
    assert client_record is not None
    assert client_record.epf_registered is True
