import pytest
from pathlib import Path
from app.ingest.structured import parse_structured
from app.ingest.unstructured import _parse_json_response, _normalise_employee

SAMPLE_CSV = Path("/Users/madhavibhat/payroll_v2/test_data/company_single_techspark.csv")


def test_parse_csv_returns_list():
    result = parse_structured(SAMPLE_CSV)
    assert isinstance(result, list)
    assert len(result) == 10


def test_parse_csv_has_required_fields():
    result = parse_structured(SAMPLE_CSV)
    required = {"name", "basic", "days_worked", "days_in_month"}
    for emp in result:
        assert required.issubset(emp.keys()), f"Missing fields in {emp}"


def test_parse_csv_numeric_types():
    result = parse_structured(SAMPLE_CSV)
    assert isinstance(result[0]["basic"], float)
    assert isinstance(result[0]["days_worked"], int)


def test_parse_invalid_file_raises():
    with pytest.raises(ValueError):
        parse_structured(Path("/tmp/nonexistent.csv"))


def test_parse_json_response_valid():
    raw = '[{"name": "Rahul", "basic": 18000, "days_worked": 31, "days_in_month": 31}]'
    result = _parse_json_response(raw)
    assert len(result) == 1
    assert result[0]["name"] == "Rahul"


def test_parse_json_response_strips_markdown():
    raw = '```json\n[{"name": "Priya", "basic": 22000}]\n```'
    result = _parse_json_response(raw)
    assert result[0]["name"] == "Priya"


def test_parse_json_response_invalid_raises():
    with pytest.raises(ValueError, match="invalid JSON"):
        _parse_json_response("not json")


def test_normalise_employee_types():
    raw = {"name": "Test", "basic": "18000", "days_worked": "31", "days_in_month": "31"}
    emp = _normalise_employee(raw)
    assert isinstance(emp["basic"], float)
    assert isinstance(emp["days_worked"], int)
    assert emp["basic"] == 18000.0
