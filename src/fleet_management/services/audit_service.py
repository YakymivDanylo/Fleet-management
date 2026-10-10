import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditEvent, UserActivity

logger = logging.getLogger("fleet_management.audit")


def add_audit_event(
    db: AsyncSession,
    event_type: str,
    actor_id: int | None,
    subject_id: int | None,
    result: str,
    correlation_id: str,
) -> AuditEvent:
    """Stage a privacy-safe audit row (ids + result only) in the caller's transaction."""
    event = AuditEvent(
        event_type=event_type,
        actor_id=actor_id,
        subject_id=subject_id,
        result=result,
        correlation_id=correlation_id,
    )
    db.add(event)
    logger.info(
        "audit event=%s actor=user:%s subject=user:%s result=%s",
        event_type,
        actor_id,
        subject_id,
        result,
    )
    return event


async def record_audit_event(
    db: AsyncSession,
    event_type: str,
    actor_id: int | None,
    subject_id: int | None,
    result: str,
    correlation_id: str,
) -> None:
    add_audit_event(db, event_type, actor_id, subject_id, result, correlation_id)
    await db.commit()


async def record_activity(
    db: AsyncSession,
    user_id: int,
    action: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    db.add(
        UserActivity(
            user_id=user_id,
            action=action,
            ip_address=ip_address,
            user_agent=user_agent[:255] if user_agent else None,
        )
    )
    await db.commit()
