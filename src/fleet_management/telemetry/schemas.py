from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class TelemetryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vehicle_id: int = Field(gt=0)
    recorded_at: AwareDatetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    fuel_level: float = Field(ge=0, le=100)
    is_locked: bool
