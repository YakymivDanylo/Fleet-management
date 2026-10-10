"""Right to Erasure (GDPR Art. 17) as irreversible anonymization in one transaction.

Entity policy (see docs/lab4-privacy-gdpr.md):
  users               ANONYMIZE  identifiers replaced by random, unrelated values
  renters             ANONYMIZE  name/licence replaced; row kept so rentals keep a valid FK
  rentals             RETAIN     business/financial record; no PII columns of its own
  telemetry_readings  RETAIN     describes vehicles, no subject PII
  user_activity       DELETE     pure PII/technical identifiers (IP, user agent)
  marketing_messages  DELETE     behavioural/outbox data
  analytics_events    DELETE     behavioural data
  user_consents       ANONYMIZE  withdrawn; rows hold no PII
  consent_history     RETAIN     proof of consent changes; ids and versions only
  audit_events        APPEND     one new PII-free event; old events hold no PII
"""

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..exceptions import NotFoundError
from ..models import AnalyticsEvent, MarketingMessage, Renter, User, UserActivity
from ..security import hash_password
from . import audit_service, consent_service

ANONYMIZED_NAME = "Anonymized User"
EVENT_TYPE = "user_anonymize"


def _anonymize_user_row(user: User, now: datetime) -> None:
    # Values are random, never derived from the originals (a hash of the e-mail would be
    # pseudonymization: anyone holding the e-mail could recompute it and re-identify).
    user.email = f"anon-{uuid.uuid4().hex}@anon.invalid"
    user.full_name = ANONYMIZED_NAME
    user.phone = None
    user.hashed_password = hash_password(secrets.token_urlsafe(32))
    user.is_active = False
    user.anonymized_at = now


async def _anonymize_renters(db: AsyncSession, user_id: int) -> int:
    renters = (await db.execute(select(Renter).where(Renter.user_id == user_id))).scalars().all()
    for renter in renters:
        renter.full_name = ANONYMIZED_NAME
        renter.license_number = f"anon-{uuid.uuid4().hex}"
    return len(renters)


async def _delete_rows(db: AsyncSession, model, user_id: int) -> int:
    result = await db.execute(delete(model).where(model.user_id == user_id))
    return result.rowcount or 0


async def _erase(db: AsyncSession, user: User, now: datetime) -> dict[str, int]:
    _anonymize_user_row(user, now)
    return {
        "renters_anonymized": await _anonymize_renters(db, user.id),
        "activity_deleted": await _delete_rows(db, UserActivity, user.id),
        "marketing_messages_deleted": await _delete_rows(db, MarketingMessage, user.id),
        "analytics_events_deleted": await _delete_rows(db, AnalyticsEvent, user.id),
        "consents_withdrawn": await consent_service.withdraw_all(db, user.id, "erasure"),
    }


async def anonymize_user(
    db: AsyncSession, subject_id: int, actor: User, correlation_id: str
) -> tuple[User, str, dict[str, int]]:
    """Anonymize `subject_id` atomically. Repeating the call is a harmless no-op."""
    subject = (
        await db.execute(select(User).where(User.id == subject_id).with_for_update())
    ).scalar_one_or_none()
    if subject is None:
        raise NotFoundError("User not found")
    if subject.anonymized_at is not None:
        await audit_service.record_audit_event(
            db, EVENT_TYPE, actor.id, subject.id, "already_anonymized", correlation_id
        )
        return subject, "already_anonymized", {}
    try:
        actions = await _erase(db, subject, datetime.now(UTC))
        audit_service.add_audit_event(
            db, EVENT_TYPE, actor.id, subject.id, "anonymized", correlation_id
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return subject, "anonymized", actions
