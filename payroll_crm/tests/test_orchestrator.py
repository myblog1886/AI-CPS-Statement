import pytest, json
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Client, Run
from app.routers.run import orchestrate, apply_text_edit

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    # Seed a client
    c = Client(name="Test Co", gstin="", esic_registered=False, epf_registered=True, state="MH")
    session.add(c)
    session.commit()
    yield session
    session.close()

SAMPLE_EMPLOYEES = [
    {"emp_id": "E001", "name": "Rahul", "basic": 18000.0, "da": 0.0, "hra": 0.0,
     "other_allowances": 0.0, "days_in_month": 30, "days_worked": 30,
     "advance_deduction": 0.0, "uan": "", "pf_number": "", "esic_number": "",
     "bank_account": "", "ifsc_code": "", "designation": "", "department": ""}
]

def test_orchestrate_creates_run(db):
    client = db.query(Client).first()
    run = orchestrate(client.id, SAMPLE_EMPLOYEES, 6, 2025, db)
    assert run.id is not None
    assert run.status == "draft"
    assert run.client_id == client.id
    assert json.loads(run.payroll_json)  # non-empty list
    assert json.loads(run.compliance_json)  # non-empty list

def test_orchestrate_sets_parent_run_id(db):
    client = db.query(Client).first()
    run1 = orchestrate(client.id, SAMPLE_EMPLOYEES, 6, 2025, db)
    run2 = orchestrate(client.id, SAMPLE_EMPLOYEES, 6, 2025, db, parent_run_id=run1.id)
    assert run2.parent_run_id == run1.id

def test_apply_text_edit_calls_claude():
    employees = [{"name": "Rahul", "basic": 18000.0}]
    patched_response = MagicMock()
    patched_response.content = [MagicMock(text='[{"name": "Rahul", "basic": 20000.0}]')]
    with patch("app.routers.run.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = patched_response
        with patch.dict("os.environ", {"CLAUDE_API_KEY": "test-key"}):
            result = apply_text_edit(employees, "increase Rahul's basic to 20000")
    assert result[0]["basic"] == 20000.0

def test_apply_text_edit_invalid_json_raises():
    patched_response = MagicMock()
    patched_response.content = [MagicMock(text="not json")]
    with patch("app.routers.run.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = patched_response
        with patch.dict("os.environ", {"CLAUDE_API_KEY": "test-key"}):
            with pytest.raises(ValueError, match="invalid JSON"):
                apply_text_edit([{"name": "x"}], "do something")
