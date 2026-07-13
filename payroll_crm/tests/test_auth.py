import sys
sys.path.insert(0, "/Users/madhavibhat/payroll_crm")
# Note: payroll_v2 and cps-compliance-platform paths added only if needed by db/models
# Keeping them out here to avoid flask_cors import collision at collection time

from app.auth import hash_password, verify_password

def test_hash_and_verify():
    h = hash_password("secret123")
    assert verify_password("secret123", h) is True
    assert verify_password("wrong", h) is False
