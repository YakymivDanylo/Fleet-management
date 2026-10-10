"""Right of Access (GDPR Art. 15): builds the personal-data export for one subject."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    AnalyticsEvent,
    MarketingMessage,
    Rental,
    Renter,
    User,
    UserActivity,
)
from ..schemas_privacy import (
    EXPORT_SCHEMA_VERSION,
    ActivityItem,
    AnalyticsItem,
    ConsentHistoryItem,
    ConsentsSection,
    MarketingItem,
    Omission,
    PersonalDataExport,
    ProfileSection,
    RentalItem,
    RenterProfileSection,
    SettingsSection,
)
from . import consent_service

DATA_CATEGORIES = [
    "profile",
    "settings",
    "renter_profile",
    "activity",
    "rentals",
    "consents",
    "marketing_messages",
    "analytics_events",
]

OMISSIONS = [
    Omission(
        category="credentials",
        reason="Password hash and tokens are security data, not personal data of the subject.",
    ),
    Omission(
        category="telemetry",
        reason="Vehicle telemetry describes vehicles and is not linked to a subject.",
    ),
    Omission(
        category="audit_events",
        reason="Audit trail holds only ids and results, kept for accountability.",
    ),
]


def utc_iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


async def _all(db: AsyncSession, stmt) -> list:
    return list((await db.execute(stmt)).scalars().all())


async def _rentals_of(db: AsyncSession, renter: Renter | None) -> list[Rental]:
    if renter is None:
        return []
    return await _all(db, select(Rental).where(Rental.renter_id == renter.id).order_by(Rental.id))


async def build_export(db: AsyncSession, subject: User) -> PersonalDataExport:
    uid = subject.id
    renter = (await db.execute(select(Renter).where(Renter.user_id == uid))).scalar_one_or_none()
    activity = await _all(
        db, select(UserActivity).where(UserActivity.user_id == uid).order_by(UserActivity.id)
    )
    marketing = await _all(
        db,
        select(MarketingMessage)
        .where(MarketingMessage.user_id == uid)
        .order_by(MarketingMessage.id),
    )
    analytics = await _all(
        db, select(AnalyticsEvent).where(AnalyticsEvent.user_id == uid).order_by(AnalyticsEvent.id)
    )
    history = await consent_service.list_history(db, uid)
    return PersonalDataExport(
        schema_version=EXPORT_SCHEMA_VERSION,
        generated_at=utc_iso(datetime.now(UTC)),
        subject_id=uid,
        data_categories=DATA_CATEGORIES,
        profile=ProfileSection.model_validate(subject),
        settings=SettingsSection(
            role=str(subject.role),
            is_active=subject.is_active,
            anonymized=subject.anonymized_at is not None,
        ),
        renter_profile=RenterProfileSection.model_validate(renter) if renter else None,
        activity=[ActivityItem.model_validate(a) for a in activity],
        rentals=[RentalItem.model_validate(r) for r in await _rentals_of(db, renter)],
        consents=ConsentsSection(
            current=await consent_service.list_current(db, uid),
            history=[ConsentHistoryItem.model_validate(h) for h in history],
        ),
        marketing_messages=[MarketingItem.model_validate(m) for m in marketing],
        analytics_events=[AnalyticsItem.model_validate(e) for e in analytics],
        omissions=OMISSIONS,
    )
