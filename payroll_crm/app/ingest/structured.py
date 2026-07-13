from pathlib import Path
import pandas as pd

COLUMN_ALIASES = {
    "emp_id":            ["emp_id", "employee_id", "empid", "id", "sl no", "serial"],
    "name":              ["name", "employee name", "emp name", "full name"],
    "designation":       ["designation", "role", "post", "position"],
    "department":        ["department", "dept", "division"],
    "uan":               ["uan", "uan number", "uan no"],
    "pf_number":         ["pf_number", "pf number", "pf no", "epf number"],
    "esic_number":       ["esic_number", "esic number", "esic no", "ip number"],
    "basic":             ["basic", "basic salary", "basic pay", "basic wage"],
    "da":                ["da", "dearness allowance", "dearness allow"],
    "hra":               ["hra", "house rent allowance", "house rent"],
    "other_allowances":  ["other_allowances", "other allowances", "other allow", "special allowance"],
    "days_in_month":     ["days_in_month", "days in month", "total days", "working days in month"],
    "days_worked":       ["days_worked", "days worked", "attended days", "actual days", "present days"],
    "advance_deduction": ["advance_deduction", "advance", "advance deduction", "loan deduction"],
    "bank_account":      ["bank_account", "bank account", "account number", "acc no"],
    "ifsc_code":         ["ifsc_code", "ifsc", "ifsc code"],
}

NUMERIC_FIELDS = ["basic", "da", "hra", "other_allowances", "advance_deduction"]
INT_FIELDS = ["days_in_month", "days_worked"]
STRING_FIELDS = ["emp_id", "name", "uan", "pf_number", "esic_number",
                 "bank_account", "ifsc_code", "designation", "department"]


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    lower_cols = {c.lower().strip(): c for c in df.columns}
    rename = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lower_cols:
                rename[lower_cols[alias]] = canonical
                break
    return df.rename(columns=rename)


def parse_structured(path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        raise ValueError(f"File not found: {path}")
    try:
        if path.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(path)
        elif path.suffix.lower() == ".csv":
            df = pd.read_csv(path)
        else:
            raise ValueError(f"Unsupported format: {path.suffix}. Use CSV or Excel.")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Could not read file: {e}")

    df = _normalise_columns(df)
    df = df.dropna(how="all")

    if "name" not in df.columns:
        raise ValueError("Could not find an employee name column. Check column headers.")
    if "basic" not in df.columns:
        raise ValueError("Could not find a basic salary column. Check column headers.")

    for f in NUMERIC_FIELDS:
        if f in df.columns:
            df[f] = pd.to_numeric(df[f], errors="coerce").fillna(0).astype(float)
        else:
            df[f] = 0.0

    for f in INT_FIELDS:
        if f in df.columns:
            df[f] = pd.to_numeric(df[f], errors="coerce").fillna(30).astype(int)
        else:
            df[f] = 30

    for f in STRING_FIELDS:
        if f not in df.columns:
            df[f] = ""

    records = df.to_dict(orient="records")
    all_fields = STRING_FIELDS + NUMERIC_FIELDS + INT_FIELDS
    return [
        {f: (str(row.get(f, "")) if f in STRING_FIELDS else row.get(f, 0))
         for f in all_fields}
        for row in records
        if str(row.get("name", "")).strip()
    ]
