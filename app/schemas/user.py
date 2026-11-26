import re
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import VALID_ROLES

# Admin accounts are created with `python -m app.cli create-admin`, never self-registered.
SELF_REGISTER_ROLES = VALID_ROLES - {"admin"}


class UserRegister(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    phone_number: str
    email: EmailStr | None = None
    password: str = Field(min_length=8, max_length=128)
    role: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = re.sub(r"[\s-]", "", v)
        if not re.match(r"^\+?[0-9]{7,15}$", v):
            raise ValueError("Invalid phone number format")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in SELF_REGISTER_ROLES:
            raise ValueError(f"Role must be one of: {', '.join(sorted(SELF_REGISTER_ROLES))}")
        return v


class UserLogin(BaseModel):
    phone_number: str
    password: str


class RoleOut(BaseModel):
    role: str
    verified: bool

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: UUID
    full_name: str
    phone_number: str
    email: str | None
    is_active: bool
    phone_verified: bool
    roles: list[RoleOut] = []

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
