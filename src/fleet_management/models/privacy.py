"""Privacy-engineering tables: consent, activity history, audit, consent-gated data."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ConsentPurpose(enum.StrEnum):
    MARKETING_EMAIL = "MARKETING_EMAIL"
    OPTIONAL_ANALYTICS = "OPTIONAL_ANALYTICS"
    PERSONALIZATION = "PERSONALIZATION"


class ConsentStatus(enum.StrEnum):
    GRANTED = "GRANTED"
    WITHDRAWN = "WITHDRAWN"


class ConsentAction(enum.StrEnum):
    GRANT = "GRANT"
    REVOKE = "REVOKE"


class MarketingStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    SKIPPED = "SKIPPED"


def _text_enum(enum_cls: type[enum.Enum]) -> SAEnum:
    # VARCHAR instead of a native PG enum: purposes/actions can grow without type migrations.
    return SAEnum(enum_cls, native_enum=False, length=30)


class UserConsent(Base):
    """Current consent state: exactly one row per (user, purpose)."""

    __tablename__ = "user_consents"
    __table_args__ = (UniqueConstraint("user_id", "purpose", name="uq_user_consents_user_purpose"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[ConsentPurpose] = mapped_column(_text_enum(ConsentPurpose))
    status: Mapped[ConsentStatus] = mapped_column(_text_enum(ConsentStatus))
    policy_version: Mapped[str] = mapped_column(String(20))
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(50))


class ConsentHistory(Base):
    """Append-only evidence log: which policy version, through which channel, when."""

    __tablename__ = "consent_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[ConsentPurpose] = mapped_column(_text_enum(ConsentPurpose))
    action: Mapped[ConsentAction] = mapped_column(_text_enum(ConsentAction))
    policy_version: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(50))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserActivity(Base):
    """Account activity history; ip_address/user_agent model technical identifiers."""

    __tablename__ = "user_activity"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AuditEvent(Base):
    """Privacy-safe audit trail: ids, result and correlation id only — never PII values."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    actor_id: Mapped[int | None] = mapped_column(nullable=True)
    subject_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    result: Mapped[str] = mapped_column(String(64))
    correlation_id: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MarketingMessage(Base):
    """Outbox of consent-gated marketing e-mails. Stores no address: it is resolved at send time."""

    __tablename__ = "marketing_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    campaign: Mapped[str] = mapped_column(String(64))
    status: Mapped[MarketingStatus] = mapped_column(
        _text_enum(MarketingStatus), default=MarketingStatus.QUEUED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnalyticsEvent(Base):
    """Optional behavioural analytics, recorded only while OPTIONAL_ANALYTICS consent is granted."""

    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_name: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
