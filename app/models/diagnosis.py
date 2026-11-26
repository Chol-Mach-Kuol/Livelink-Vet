import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    veterinarian_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    disease_name = Column(String(150), nullable=True)
    diagnosis_status = Column(String(30), nullable=False)  # suspected | provisional | confirmed | ruled_out
    diagnostic_method = Column(String(50), nullable=True)  # clinical_examination | laboratory_test | epidemiological_investigation | other
    clinical_notes = Column(Text, nullable=True)
    diagnosed_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    case = relationship("Case", back_populates="diagnoses")
    veterinarian = relationship("User", foreign_keys=[veterinarian_id])


class LabResult(Base):
    __tablename__ = "lab_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    laboratory_name = Column(String(150), nullable=True)
    test_name = Column(String(150), nullable=True)
    sample_type = Column(String(100), nullable=True)
    result = Column(Text, nullable=False)
    result_date = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    organization_type = Column(String(50), nullable=True)
    location_id = Column(UUID(as_uuid=True), ForeignKey("locations.id"), nullable=True)
    contact_email = Column(String(150), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
