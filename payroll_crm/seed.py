import sys
# payroll_crm must be first so 'app' resolves to payroll_crm/app/, not cps-compliance-platform/app.py
sys.path.insert(0, "/Users/madhavibhat/payroll_crm")
sys.path.append("/Users/madhavibhat/payroll_v2")
sys.path.append("/Users/madhavibhat/cps-compliance-platform")

import sqlalchemy
from app.db import engine, SessionLocal
from app.models import Base, User
from app.auth import hash_password

Base.metadata.create_all(engine)
with SessionLocal() as s:
    existing = s.execute(sqlalchemy.select(User).where(User.email == "admin@cps.in")).scalar_one_or_none()
    if not existing:
        s.add(User(email="admin@cps.in", password_hash=hash_password("admin123").decode(), role="operator"))
        s.commit()
        print("Operator created: admin@cps.in / admin123")
    else:
        print("Already exists")
