"""Response contracts for the privacy API. Explicit models double as an allow-list of fields."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from .models import ConsentAction, ConsentPurpose, ConsentStatus

EXPORT_SCHEMA_VERSION = "1.0"


def _as_utc(value: datetime) -> datetime:
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value).astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]


class _Model(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProfileSection(_Model):
    id: int
    email: str
    full_name: str
    phone: str | None
    created_at: UtcDatetime


class SettingsSection(_Model):
    role: str
    is_active: bool
    anonymized: bool


class RenterProfileSection(_Model):
    id: int
    full_name: str
    license_number: str


class ActivityItem(_Model):
    action: str
    occurred_at: UtcDatetime
    ip_address: str | None
    user_agent: str | None


class RentalItem(_Model):
    id: int
    vehicle_id: int
    start_station_id: int
    end_station_id: int | None
    started_at: UtcDatetime
    ended_at: UtcDatetime | None
    status: str


class ConsentCurrentItem(_Model):
    purpose: ConsentPurpose
    status: ConsentStatus
    policy_version: str
    granted_at: UtcDatetime | None
    withdrawn_at: UtcDatetime | None
    updated_at: UtcDatetime
    source: str


class ConsentHistoryItem(_Model):
    purpose: ConsentPurpose
    action: ConsentAction
    policy_version: str
    source: str
    occurred_at: UtcDatetime


class ConsentsSection(_Model):
    current: list[ConsentCurrentItem]
    history: list[ConsentHistoryItem]


class MarketingItem(_Model):
    campaign: str
    status: str
    created_at: UtcDatetime
    processed_at: UtcDatetime | None


class AnalyticsItem(_Model):
    event_name: str
    occurred_at: UtcDatetime


class Omission(_Model):
    category: str
    reason: str


class PersonalDataExport(_Model):
    schema_version: Literal["1.0"] = EXPORT_SCHEMA_VERSION
    generated_at: str = Field(description="UTC timestamp, ISO 8601 with Z suffix")
    subject_id: int
    data_categories: list[str]
    profile: ProfileSection
    settings: SettingsSection
    renter_profile: RenterProfileSection | None
    activity: list[ActivityItem]
    rentals: list[RentalItem]
    consents: ConsentsSection
    marketing_messages: list[MarketingItem]
    analytics_events: list[AnalyticsItem]
    omissions: list[Omission]


class ConsentGrantRequest(BaseModel):
    policy_version: str = Field(min_length=1, max_length=20)
    source: str = Field(default="api", min_length=1, max_length=50)


class ConsentRevokeRequest(BaseModel):
    source: str = Field(default="api", min_length=1, max_length=50)


class ConsentState(BaseModel):
    purpose: ConsentPurpose
    status: ConsentStatus | Literal["NONE"]
    policy_version: str | None = None
    granted_at: UtcDatetime | None = None
    withdrawn_at: UtcDatetime | None = None
    updated_at: UtcDatetime | None = None
    source: str | None = None
    changed: bool


class ConsentOverview(BaseModel):
    current: list[ConsentCurrentItem]
    history: list[ConsentHistoryItem]


class MarketingRequest(BaseModel):
    campaign: str = Field(min_length=1, max_length=64)


class AnalyticsRequest(BaseModel):
    event_name: str = Field(min_length=1, max_length=64)


class RenterProfileRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    license_number: str = Field(min_length=1, max_length=50)


class AnonymizeResult(BaseModel):
    subject_id: int
    status: Literal["anonymized", "already_anonymized"]
    anonymized_at: UtcDatetime
    actions: dict[str, int]
