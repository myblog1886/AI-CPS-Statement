from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean,
    ForeignKey, Text, CheckConstraint
)
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase):
    pass

class Client(Base):
    __tablename__ = "clients"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    name             = Column(String, nullable=False)
    establishment_id = Column(String)
    gstin            = Column(String)
    state            = Column(String, nullable=False)
    industry_type    = Column(String)
    headcount        = Column(Integer)
    esic_registered  = Column(Boolean, default=False)
    epf_registered   = Column(Boolean, default=False)
    created_at       = Column(DateTime, default=datetime.utcnow)
    users            = relationship("User", back_populates="client")
    runs             = relationship("Run", back_populates="client")

class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    email         = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role          = Column(String, nullable=False)
    client_id     = Column(Integer, ForeignKey("clients.id"), nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    client        = relationship("Client", back_populates="users")
    __table_args__ = (CheckConstraint("role IN ('operator','client')"),)

class Run(Base):
    __tablename__ = "runs"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    client_id        = Column(Integer, ForeignKey("clients.id"), nullable=False)
    month            = Column(Integer, nullable=False)
    year             = Column(Integer, nullable=False)
    version          = Column(Integer, nullable=False, default=1)
    status           = Column(String, nullable=False, default="draft")
    payroll_json     = Column(Text)   # JSON: list of payroll result dicts
    compliance_json  = Column(Text)   # JSON: list of finding dicts
    parent_run_id    = Column(Integer, ForeignKey("runs.id"), nullable=True)
    created_by       = Column(Integer, ForeignKey("users.id"))
    approved_by      = Column(Integer, ForeignKey("users.id"))
    approved_at      = Column(DateTime)
    created_at       = Column(DateTime, default=datetime.utcnow)
    client           = relationship("Client", back_populates="runs")
    files            = relationship("RunFile", back_populates="run")
    edit_requests    = relationship("EditRequest", back_populates="run")
    outputs          = relationship("Output", back_populates="run")
    __table_args__   = (CheckConstraint("status IN ('draft','approved','error')"),)

class RunFile(Base):
    __tablename__ = "run_files"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    run_id        = Column(Integer, ForeignKey("runs.id"), nullable=False)
    file_type     = Column(String)
    filename      = Column(String)
    original_name = Column(String)
    storage_path  = Column(String, nullable=False, default="")
    created_at    = Column(DateTime, default=datetime.utcnow)
    run           = relationship("Run", back_populates="files")

class EditRequest(Base):
    __tablename__ = "edit_requests"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    run_id     = Column(Integer, ForeignKey("runs.id"), nullable=False)
    type       = Column(String, nullable=False)
    content    = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    run        = relationship("Run", back_populates="edit_requests")
    __table_args__ = (CheckConstraint("type IN ('text','reupload')"),)

class Output(Base):
    __tablename__ = "outputs"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    run_id       = Column(Integer, ForeignKey("runs.id"), nullable=False)
    output_type  = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    created_at   = Column(DateTime, default=datetime.utcnow)
    run          = relationship("Run", back_populates="outputs")
    __table_args__ = (CheckConstraint("output_type IN ('ecr','esic','slips','bank','compliance')"),)
