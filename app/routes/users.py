from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.activity import AuditLog, Notification
from app.models.user import RoleAssignment, User, VALID_ROLES
from app.permissions.access_control import require_role
from app.schemas.user import UserOut
from app.services import audit

router = APIRouter(prefix="/users", tags=["admin"])


@router.get("", response_model=list[UserOut])
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    pending_verification: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    query = db.query(User)
    if pending_verification:
        query = query.join(RoleAssignment).filter(RoleAssignment.verified.is_(False)).distinct()
    return query.offset(skip).limit(limit).all()


@router.post("/{user_id}/verify-role/{role}")
def verify_user_role(
    user_id: UUID,
    role: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    assignment = db.query(RoleAssignment).filter_by(user_id=user_id, role=role).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Role assignment not found")
    assignment.verified = True
    audit.record(db, current_user, "user.role_verified", "user", user_id, role=role)
    db.commit()
    return {"message": f"Role '{role}' verified for user {user_id}"}


@router.post("/{user_id}/deactivate")
def deactivate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    user.is_active = False
    audit.record(db, current_user, "user.deactivated", "user", user_id)
    db.commit()
    return {"message": "User deactivated"}


@router.get("/audit-log")
def audit_log(
    entity_type: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    query = db.query(AuditLog)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    return [
        {"at": e.created_at, "actor_id": e.actor_id, "action": e.action,
         "entity_type": e.entity_type, "entity_id": e.entity_id, "details": e.details}
        for e in query.order_by(AuditLog.created_at.desc()).limit(limit)
    ]


@router.get("/notifications")
def notifications(
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    return [
        {"at": n.created_at, "phone_number": n.phone_number, "reason": n.reason,
         "status": n.status, "message": n.message, "error": n.error}
        for n in db.query(Notification).order_by(Notification.created_at.desc()).limit(limit)
    ]
