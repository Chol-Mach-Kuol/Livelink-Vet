from uuid import UUID
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

CaseStatus = Literal["open", "investigating", "awaiting_lab", "diagnosed", "monitoring", "resolved", "closed"]
Priority = Literal["low", "normal", "high", "urgent"]
AssignmentRole = Literal["lead_veterinarian", "animal_health_worker", "student", "researcher"]


class CaseCreate(BaseModel):
    location_id: UUID
    priority: Priority = "normal"
    report_ids: list[UUID] = Field(default_factory=list, description="Reports to link immediately")


class CaseFromCluster(BaseModel):
    report_ids: list[UUID] = Field(min_length=1)
    priority: Priority | None = None


class CaseStatusUpdate(BaseModel):
    case_status: CaseStatus
    note: str | None = Field(default=None, max_length=2000)


class CaseAssignmentCreate(BaseModel):
    user_id: UUID
    assignment_role: AssignmentRole


class CaseOut(BaseModel):
    id: UUID
    case_number: str
    location_id: UUID
    assigned_vet_id: UUID | None
    case_status: str
    priority: str
    opened_at: datetime
    closed_at: datetime | None

    model_config = {"from_attributes": True}


class TimelineEvent(BaseModel):
    at: datetime
    action: str
    actor_id: UUID | None
    details: dict | None
