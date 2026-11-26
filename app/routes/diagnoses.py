from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.diagnosis import Diagnosis, LabResult
from app.models.user import User
from app.permissions.access_control import get_current_user, require_role
from app.routes.cases import get_visible_case
from app.schemas.diagnosis import DiagnosisCreate, DiagnosisOut, LabResultCreate, LabResultOut
from app.services import audit, case_service

router = APIRouter(prefix="/cases", tags=["diagnoses"])


@router.post("/{case_id}/diagnoses", response_model=DiagnosisOut, status_code=status.HTTP_201_CREATED)
def create_diagnosis(
    case_id: UUID,
    payload: DiagnosisCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("veterinarian")),
):
    case = get_visible_case(db, case_id, current_user)
    diagnosis = Diagnosis(case_id=case.id, veterinarian_id=current_user.id, **payload.model_dump())
    db.add(diagnosis)
    db.flush()
    audit.record(db, current_user, "case.diagnosis_recorded", "case", case.id,
                 diagnosis_id=diagnosis.id, disease=payload.disease_name, status=payload.diagnosis_status)
    # A confirmed diagnosis moves the case forward when the lifecycle allows it.
    if payload.diagnosis_status == "confirmed" and case_service.can_transition(case.case_status, "diagnosed"):
        audit.record(db, current_user, "case.status_changed", "case", case.id,
                     **{"from": case.case_status, "to": "diagnosed", "note": "auto: confirmed diagnosis"})
        case.case_status = "diagnosed"
    db.commit()
    db.refresh(diagnosis)
    return diagnosis


@router.get("/{case_id}/diagnoses", response_model=list[DiagnosisOut])
def list_diagnoses(case_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    get_visible_case(db, case_id, current_user)
    return db.query(Diagnosis).filter(Diagnosis.case_id == case_id).order_by(Diagnosis.diagnosed_at).all()


@router.post("/{case_id}/lab-results", response_model=LabResultOut, status_code=status.HTTP_201_CREATED)
def add_lab_result(
    case_id: UUID,
    payload: LabResultCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("veterinarian", "admin")),
):
    case = get_visible_case(db, case_id, current_user)
    result = LabResult(case_id=case.id, verified_by=current_user.id, **payload.model_dump())
    db.add(result)
    db.flush()
    audit.record(db, current_user, "case.lab_result_added", "case", case.id,
                 lab_result_id=result.id, test=payload.test_name)
    db.commit()
    db.refresh(result)
    return result


@router.get("/{case_id}/lab-results", response_model=list[LabResultOut])
def list_lab_results(case_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    get_visible_case(db, case_id, current_user)
    return db.query(LabResult).filter(LabResult.case_id == case_id).order_by(LabResult.created_at).all()
