import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class Case(Base):
    __tablename__ = "cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_number = Column(String(40), unique=True, nullable=False)
    location_id = Column(UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False)
    assigned_vet_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    case_status = Column(String(30), default="open")
    priority = Column(String(20), default="normal")
    opened_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)

    location = relationship("Location")
    assigned_vet = relationship("User", foreign_keys=[assigned_vet_id])
    diagnoses = relationship("Diagnosis", back_populates="case")


class CaseReport(Base):
    __tablename__ = "case_reports"

    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), primary_key=True)
    report_id = Column(UUID(as_uuid=True), ForeignKey("disease_reports.id"), primary_key=True, unique=True)


class CaseAssignment(Base):
    __tablename__ = "case_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    assignment_role = Column(String(30), nullable=False)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
