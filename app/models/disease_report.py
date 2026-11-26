import uuid
from sqlalchemy import JSON, Boolean, Column, String, Integer, Numeric, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

REPORT_STATUSES = ("submitted", "under_review", "linked_to_case", "closed")
REPORT_CHANNELS = ("app", "ussd", "sms", "offline_sync")


class DiseaseReport(Base):
    __tablename__ = "disease_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Client-generated id so devices that sync after being offline never create duplicates.
    client_ref = Column(String(64), unique=True, nullable=True, index=True)
    reporter_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    location_id = Column(UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False)
    species = Column(String(30), default="cattle")
    signs = Column(JSON, default=list)  # standardised clinical sign codes (see services.triage.SIGNS)
    symptoms = Column(Text, nullable=False)  # free-text description in the reporter's words
    affected_count = Column(Integer, nullable=False)
    death_count = Column(Integer, default=0)
    first_observed_at = Column(DateTime(timezone=True), nullable=True)
    description = Column(Text, nullable=True)
    # Optional GPS fix from the reporting device — more precise than the location record.
    latitude = Column(Numeric(10, 7), nullable=True)
    longitude = Column(Numeric(10, 7), nullable=True)
    channel = Column(String(20), default="app")
    report_status = Column(String(30), default="submitted")

    # Syndromic triage output (decision support only — never a diagnosis).
    triage = Column(JSON, nullable=True)
    suggested_priority = Column(String(20), default="normal")
    zoonotic_alert = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    reporter = relationship("User", back_populates="reports")
    location = relationship("Location")
