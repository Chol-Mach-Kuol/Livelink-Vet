from sqlalchemy.orm import Session

from app.models.activity import AuditLog


def record(db: Session, actor, action: str, entity_type: str, entity_id=None, **details) -> None:
    """Add an audit entry to the current transaction (committed with the change it describes)."""
    db.add(AuditLog(
        actor_id=getattr(actor, "id", None),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details={k: (str(v) if not isinstance(v, (int, float, bool, list, dict, type(None))) else v)
                 for k, v in details.items()} or None,
    ))
