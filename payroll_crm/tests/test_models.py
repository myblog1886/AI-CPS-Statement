import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, Client, User, Run

@pytest.fixture
def session():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as s:
        yield s

def test_create_client_and_user(session):
    c = Client(name="Test Co", state="Maharashtra", establishment_id="MH/MUM/001")
    session.add(c)
    session.flush()
    u = User(email="a@b.com", password_hash="x", role="client", client_id=c.id)
    session.add(u)
    session.commit()
    assert session.get(Client, c.id).name == "Test Co"
    assert session.get(User, u.id).role == "client"

def test_create_run(session):
    c = Client(name="Co", state="Maharashtra")
    session.add(c); session.flush()
    r = Run(client_id=c.id, month=6, year=2026)
    session.add(r); session.commit()
    assert session.get(Run, r.id).status == "draft"
    assert session.get(Run, r.id).version == 1
