"""Purpose-specific consent management and the Consent Policy Gate."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    ConsentAction,
    ConsentHistory,
    ConsentPurpose,
    ConsentStatus,
    UserConsent,
)

CURRENT_POLICY_VERSION = "2026-01"

REASON_GRANTED = "granted"
REASON_MISSING = "no_consent_on_record"
REASON_WITHDRAWN = "consent_withdrawn"
REASON_VERSION = "policy_version_mismatch"


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str

    @property
    def label(self) -> str:
        return "ALLOW" if self.allowed else "DENY"


@dataclass(frozen=True)
class ConsentChange:
    consent: UserConsent | None
    changed: bool


def _now() -> datetime:
    return datetime.now(UTC)


async def _get_current(
    db: AsyncSession, user_id: int, purpose: ConsentPurpose, lock: bool = False
) -> UserConsent | None:
    stmt = (
        select(UserConsent)
        .where(UserConsent.user_id == user_id, UserConsent.purpose == purpose)
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


def _history(
    user_id: int,
    purpose: ConsentPurpose,
    action: ConsentAction,
    policy_version: str,
    source: str,
    now: datetime,
) -> ConsentHistory:
    return ConsentHistory(
        user_id=user_id,
        purpose=purpose,
        action=action,
        policy_version=policy_version,
        source=source,
        occurred_at=now,
    )


async def _grant_once(
    db: AsyncSession, user_id: int, purpose: ConsentPurpose, policy_version: str, source: str
) -> ConsentChange:
    now = _now()
    consent = await _get_current(db, user_id, purpose, lock=True)
    if (
        consent is not None
        and consent.status == ConsentStatus.GRANTED
        and consent.policy_version == policy_version
    ):
        return ConsentChange(consent, changed=False)
    if consent is None:
        consent = UserConsent(user_id=user_id, purpose=purpose)
        db.add(consent)
    consent.status = ConsentStatus.GRANTED
    consent.policy_version = policy_version
    consent.granted_at = now
    consent.updated_at = now
    consent.source = source
    db.add(_history(user_id, purpose, ConsentAction.GRANT, policy_version, source, now))
    await db.commit()
    return ConsentChange(consent, changed=True)


async def grant(
    db: AsyncSession, user_id: int, purpose: ConsentPurpose, policy_version: str, source: str
) -> ConsentChange:
    """Idempotent: repeating GRANT for the same purpose and policy version changes nothing."""
    try:
        return await _grant_once(db, user_id, purpose, policy_version, source)
    except IntegrityError:
        # Two concurrent first-time grants raced on the unique (user, purpose) row.
        await db.rollback()
        return await _grant_once(db, user_id, purpose, policy_version, source)


async def revoke(
    db: AsyncSession, user_id: int, purpose: ConsentPurpose, source: str
) -> ConsentChange:
    """Idempotent: revoking a missing or already withdrawn consent writes nothing."""
    consent = await _get_current(db, user_id, purpose, lock=True)
    if consent is None or consent.status == ConsentStatus.WITHDRAWN:
        return ConsentChange(consent, changed=False)
    now = _now()
    consent.status = ConsentStatus.WITHDRAWN
    consent.withdrawn_at = now
    consent.updated_at = now
    consent.source = source
    db.add(_history(user_id, purpose, ConsentAction.REVOKE, consent.policy_version, source, now))
    await db.commit()
    return ConsentChange(consent, changed=True)


async def withdraw_all(db: AsyncSession, user_id: int, source: str) -> int:
    """Withdraw every granted consent in the caller's transaction (used by erasure)."""
    stmt = select(UserConsent).where(
        UserConsent.user_id == user_id, UserConsent.status == ConsentStatus.GRANTED
    )
    consents = (await db.execute(stmt)).scalars().all()
    now = _now()
    for consent in consents:
        consent.status = ConsentStatus.WITHDRAWN
        consent.withdrawn_at = now
        consent.updated_at = now
        consent.source = source
        db.add(
            _history(
                user_id, consent.purpose, ConsentAction.REVOKE, consent.policy_version, source, now
            )
        )
    return len(consents)


async def list_current(db: AsyncSession, user_id: int) -> list[UserConsent]:
    stmt = select(UserConsent).where(UserConsent.user_id == user_id).order_by(UserConsent.purpose)
    return list((await db.execute(stmt)).scalars().all())


async def list_history(db: AsyncSession, user_id: int) -> list[ConsentHistory]:
    stmt = select(ConsentHistory).where(ConsentHistory.user_id == user_id)
    return list((await db.execute(stmt.order_by(ConsentHistory.id))).scalars().all())


def _decide(consent: UserConsent | None, required_version: str) -> GateDecision:
    if consent is None:
        return GateDecision(False, REASON_MISSING)
    if consent.status != ConsentStatus.GRANTED:
        return GateDecision(False, REASON_WITHDRAWN)
    if consent.policy_version != required_version:
        return GateDecision(False, REASON_VERSION)
    return GateDecision(True, REASON_GRANTED)


class ConsentPolicyGate:
    """Decides ALLOW/DENY from the consent row read fresh from the DB at call time.

    Nothing is cached, so a REVOKE takes effect for the very next dependent action,
    including background jobs that were queued before the withdrawal.
    """

    @staticmethod
    async def check(
        db: AsyncSession,
        user_id: int,
        purpose: ConsentPurpose,
        required_version: str = CURRENT_POLICY_VERSION,
    ) -> GateDecision:
        consent = await _get_current(db, user_id, purpose)
        return _decide(consent, required_version)
