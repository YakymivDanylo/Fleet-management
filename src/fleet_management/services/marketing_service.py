"""Consent-dependent (optional) actions. Contract functions such as rentals skip the gate."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..exceptions import ConsentDeniedError
from ..models import (
    AnalyticsEvent,
    ConsentPurpose,
    MarketingMessage,
    MarketingStatus,
)
from . import audit_service
from .consent_service import ConsentPolicyGate


async def _require_consent(
    db: AsyncSession, user_id: int, purpose: ConsentPurpose, actor_id: int, correlation_id: str
) -> None:
    decision = await ConsentPolicyGate.check(db, user_id, purpose)
    if decision.allowed:
        return
    await audit_service.record_audit_event(
        db,
        f"{purpose.value.lower()}_action",
        actor_id,
        user_id,
        f"DENY:{decision.reason}",
        correlation_id,
    )
    raise ConsentDeniedError(purpose.value, decision.reason)


async def enqueue_marketing_email(
    db: AsyncSession, user_id: int, campaign: str, actor_id: int, correlation_id: str
) -> MarketingMessage:
    await _require_consent(db, user_id, ConsentPurpose.MARKETING_EMAIL, actor_id, correlation_id)
    message = MarketingMessage(user_id=user_id, campaign=campaign)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def record_analytics_event(
    db: AsyncSession, user_id: int, event_name: str, actor_id: int, correlation_id: str
) -> AnalyticsEvent:
    await _require_consent(db, user_id, ConsentPurpose.OPTIONAL_ANALYTICS, actor_id, correlation_id)
    event = AnalyticsEvent(user_id=user_id, event_name=event_name)
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def dispatch_pending_marketing(db: AsyncSession) -> dict[str, int]:
    """Background job: consent is re-checked per queued item, right before it is 'sent'."""
    queued = (
        (
            await db.execute(
                select(MarketingMessage).where(MarketingMessage.status == MarketingStatus.QUEUED)
            )
        )
        .scalars()
        .all()
    )
    counts = {"sent": 0, "skipped": 0}
    for message in queued:
        decision = await ConsentPolicyGate.check(
            db, message.user_id, ConsentPurpose.MARKETING_EMAIL
        )
        message.status = MarketingStatus.SENT if decision.allowed else MarketingStatus.SKIPPED
        message.processed_at = datetime.now(UTC)
        counts["sent" if decision.allowed else "skipped"] += 1
    await db.commit()
    return counts
