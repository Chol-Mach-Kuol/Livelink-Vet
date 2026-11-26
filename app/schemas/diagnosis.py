from uuid import UUID
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

DiagnosisStatus = Literal["suspected", "provisional", "confirmed", "ruled_out"]
DiagnosticMethod = Literal["clinical_examination", "laboratory_test", "epidemiological_investigation", "other"]


class DiagnosisCreate(BaseModel):
    disease_name: str | None = Field(default=None, max_length=150)
    diagnosis_status: DiagnosisStatus
    diagnostic_method: DiagnosticMethod | None = None
    clinical_notes: str | None = None


class DiagnosisOut(BaseModel):
    id: UUID
    case_id: UUID
    veterinarian_id: UUID
    disease_name: str | None
    diagnosis_status: str
    diagnostic_method: str | None
    clinical_notes: str | None
    diagnosed_at: datetime

    model_config = {"from_attributes": True}


class LabResultCreate(BaseModel):
    laboratory_name: str | None = None
    test_name: str | None = None
    sample_type: str | None = None
    result: str = Field(min_length=1)
    result_date: datetime | None = None


class LabResultOut(BaseModel):
    id: UUID
    case_id: UUID
    laboratory_name: str | None
    test_name: str | None
    sample_type: str | None
    result: str
    result_date: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
