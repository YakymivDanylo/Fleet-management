"""Consent-dependent (optional) actions. Contract functions such as rentals skip the gate."""

from collections import Counter
from dataclasses import dataclass
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


@dataclass(frozen=True)
class DispatchOutcome:
    """Value Object: the immutable verdict for one queued message.

    The consent decision and the processing instant are fixed at construction; the ORM row is
    touched only by ``apply``, after every verdict of the batch exists.
    """

    message: MarketingMessage
    allowed: bool
    processed_at: datetime

    @property
    def status(self) -> MarketingStatus:
        return MarketingStatus.SENT if self.allowed else MarketingStatus.SKIPPED

    def apply(self) -> None:
        self.message.status = self.status
        self.message.processed_at = self.processed_at


async def _verdict(
    db: AsyncSession, message: MarketingMessage, processed_at: datetime
) -> DispatchOutcome:
    decision = await ConsentPolicyGate.check(db, message.user_id, ConsentPurpose.MARKETING_EMAIL)
    return DispatchOutcome(message, decision.allowed, processed_at)


async def _decide_queue(db: AsyncSession, processed_at: datetime) -> tuple[DispatchOutcome, ...]:
    queued = (
        (
            await db.execute(
                select(MarketingMessage).where(MarketingMessage.status == MarketingStatus.QUEUED)
            )
        )
        .scalars()
        .all()
    )
    return tuple([await _verdict(db, message, processed_at) for message in queued])


def _summary(outcomes: tuple[DispatchOutcome, ...]) -> dict[str, int]:
    tally = Counter(outcome.status for outcome in outcomes)
    return {"sent": tally[MarketingStatus.SENT], "skipped": tally[MarketingStatus.SKIPPED]}


async def dispatch_pending_marketing(db: AsyncSession) -> dict[str, int]:
    """Background job: consent is re-checked per queued item, right before it is 'sent'.

    Decide first (pure, one shared timestamp), mutate rows second: a gate failure midway leaves
    every message untouched.
    """
    outcomes = await _decide_queue(db, datetime.now(UTC))
    for outcome in outcomes:
        outcome.apply()
    await db.commit()
    return _summary(outcomes)
