from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.triage import SIGNS, SPECIES


class ReportCreate(BaseModel):
    location_id: UUID
    species: str = "cattle"
    signs: list[str] = Field(default_factory=list, description="Standard sign codes from GET /reports/signs")
    symptoms: str = Field(min_length=2, max_length=2000)
    affected_count: int = Field(ge=1, le=100_000)
    death_count: int = Field(default=0, ge=0)
    first_observed_at: datetime | None = None
    description: str | None = Field(default=None, max_length=5000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    client_ref: str | None = Field(default=None, min_length=8, max_length=64,
                                   description="Device-generated id; resubmitting the same id is a no-op")

    @field_validator("species")
    @classmethod
    def valid_species(cls, v: str) -> str:
        if v not in SPECIES:
            raise ValueError(f"species must be one of: {', '.join(SPECIES)}")
        return v

    @field_validator("signs")
    @classmethod
    def valid_signs(cls, v: list[str]) -> list[str]:
        unknown = set(v) - SIGNS.keys()
        if unknown:
            raise ValueError(f"unknown sign codes: {', '.join(sorted(unknown))}")
        return sorted(set(v))

    @model_validator(mode="after")
    def check_consistency(self) -> "ReportCreate":
        if self.death_count > self.affected_count:
            raise ValueError("death_count cannot exceed affected_count")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be given together")
        return self


class ReportBatch(BaseModel):
    reports: list[ReportCreate] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def require_client_refs(self) -> "ReportBatch":
        if any(not r.client_ref for r in self.reports):
            raise ValueError("every report in a batch needs a client_ref for safe retries")
        return self


class TriageSignal(BaseModel):
    disease: str
    name: str
    match_strength: float
    matched_signs: list[str]
    zoonotic: bool
    woah_listed: bool


class TriageOut(BaseModel):
    signals: list[TriageSignal]
    red_flags: list[str]
    suggested_priority: str
    zoonotic_alert: bool
    detected_signs: list[str]
    advice: list[str]
    disclaimer: str


class ReportOut(BaseModel):
    id: UUID
    client_ref: str | None = None
    location_id: UUID
    species: str
    signs: list[str]
    symptoms: str
    affected_count: int
    death_count: int
    channel: str
    report_status: str
    suggested_priority: str
    zoonotic_alert: bool
    triage: TriageOut | None
    created_at: datetime

    model_config = {"from_attributes": True}


class BatchResultItem(BaseModel):
    client_ref: str
    id: UUID
    created: bool


class TriagePreviewIn(BaseModel):
    species: str = "cattle"
    signs: list[str] = Field(default_factory=list)
    symptoms: str | None = None
    affected_count: int = 0
    death_count: int = 0
