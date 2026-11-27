from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core import ratelimit
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User, RoleAssignment
from app.schemas.user import UserRegister, UserLogin, UserOut, TokenOut
from app.permissions.access_control import get_current_user
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.phone_number == payload.phone_number).first()
    if user and user.password_hash:
        raise HTTPException(status_code=400, detail="Phone number already registered")
    if payload.email and db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    if user:
        # Account was created automatically by a USSD report; let the owner claim it.
        user.full_name = payload.full_name
        user.email = payload.email
        user.password_hash = hash_password(payload.password)
    else:
        user = User(
            full_name=payload.full_name,
            phone_number=payload.phone_number,
            email=payload.email,
            password_hash=hash_password(payload.password),
        )
        db.add(user)
        db.flush()

    if not any(r.role == payload.role for r in user.roles):
        # Cattle keepers need no vetting; professional roles wait for an administrator.
        db.add(RoleAssignment(user_id=user.id, role=payload.role, verified=payload.role == "cattle_keeper"))
    audit.record(db, user, "user.registered", "user", user.id, role=payload.role)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)):
    keys = (f"phone:{payload.phone_number}", f"ip:{request.client.host if request.client else '?'}")
    wait = ratelimit.retry_after(*keys)
    if wait:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.",
                            headers={"Retry-After": str(wait)})
    user = db.query(User).filter(User.phone_number == payload.phone_number).first()
    if not user or not verify_password(payload.password, user.password_hash):
        ratelimit.record_failure(*keys)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    ratelimit.reset(keys[0])
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    return TokenOut(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
