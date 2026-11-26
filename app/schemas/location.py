from uuid import UUID
from pydantic import BaseModel, Field, model_validator


class LocationCreate(BaseModel):
    state: str = Field(min_length=2, max_length=100)
    county: str | None = Field(default=None, max_length=100)
    payam: str | None = Field(default=None, max_length=100)
    boma: str | None = Field(default=None, max_length=100)
    cattle_camp: str | None = Field(default=None, max_length=150)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def coords_together(self) -> "LocationCreate":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be given together")
        return self


class LocationOut(BaseModel):
    id: UUID
    state: str
    county: str | None
    payam: str | None
    boma: str | None
    cattle_camp: str | None
    latitude: float | None
    longitude: float | None

    model_config = {"from_attributes": True}
