"""GDPR endpoints: personal-data export, anonymization, consent management and gated actions.

Access rule: only the subject themself or an admin may act on /api/users/{id}/...
Anyone else gets the same 404 as for a non-existent id, so the response never reveals
whether another account exists.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user, require_admin
from ..database import get_db
from ..exceptions import NotFoundError
from ..models import ConsentPurpose, Renter, User, UserRole
from ..privacy import current_correlation_id
from ..schemas_privacy import (
    AnalyticsRequest,
    AnonymizeResult,
    ConsentGrantRequest,
    ConsentOverview,
    ConsentRevokeRequest,
    ConsentState,
    MarketingRequest,
    PersonalDataExport,
    RenterProfileRequest,
)
from ..services import (
    audit_service,
    consent_service,
    erasure_service,
    export_service,
    marketing_service,
)
from ..services.consent_service import ConsentChange

router = APIRouter(prefix="/api/users", tags=["privacy"])
admin_router = APIRouter(prefix="/api/marketing", tags=["privacy"])


@dataclass(frozen=True)
class SubjectAccess:
    subject: User
    actor: User
    correlation_id: str


def subject_access(event_type: str) -> Callable[..., Awaitable[SubjectAccess]]:
    async def dependency(
        user_id: int,
        actor: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> SubjectAccess:
        correlation_id = current_correlation_id()
        allowed = actor.id == user_id or actor.role == UserRole.ADMIN
        subject = await db.get(User, user_id) if allowed else None
        if subject is None:
            result = "denied" if not allowed else "not_found"
            await audit_service.record_audit_event(
                db, event_type, actor.id, user_id, result, correlation_id
            )
            raise NotFoundError("User not found")
        return SubjectAccess(subject, actor, correlation_id)

    return dependency


def _consent_state(purpose: ConsentPurpose, change: ConsentChange) -> ConsentState:
    consent = change.consent
    if consent is None:
        return ConsentState(purpose=purpose, status="NONE", changed=change.changed)
    return ConsentState(
        purpose=purpose,
        status=consent.status,
        policy_version=consent.policy_version,
        granted_at=consent.granted_at,
        withdrawn_at=consent.withdrawn_at,
        updated_at=consent.updated_at,
        source=consent.source,
        changed=change.changed,
    )


@router.get("/{user_id}/personal-data", response_model=PersonalDataExport)
async def export_personal_data(
    access: SubjectAccess = Depends(subject_access("personal_data_export")),
    db: AsyncSession = Depends(get_db),
):
    export = await export_service.build_export(db, access.subject)
    await audit_service.record_audit_event(
        db, "personal_data_export", access.actor.id, access.subject.id, "ok", access.correlation_id
    )
    return export


@router.post("/{user_id}/anonymize", response_model=AnonymizeResult)
async def anonymize(
    access: SubjectAccess = Depends(subject_access("user_anonymize")),
    db: AsyncSession = Depends(get_db),
):
    subject, status, actions = await erasure_service.anonymize_user(
        db, access.subject.id, access.actor, access.correlation_id
    )
    return AnonymizeResult(
        subject_id=subject.id,
        status=status,
        anonymized_at=subject.anonymized_at,
        actions=actions,
    )


@router.post("/{user_id}/renter-profile", status_code=201)
async def create_renter_profile(
    payload: RenterProfileRequest,
    access: SubjectAccess = Depends(subject_access("renter_profile_create")),
    db: AsyncSession = Depends(get_db),
):
    """Links a renter profile (name + licence number) to the account."""
    renter = Renter(
        full_name=payload.full_name,
        license_number=payload.license_number,
        user_id=access.subject.id,
    )
    db.add(renter)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="Renter profile already exists or licence number is taken"
        ) from None
    return {"renter_id": renter.id}


@router.get("/{user_id}/consents", response_model=ConsentOverview)
async def list_consents(
    access: SubjectAccess = Depends(subject_access("consent_list")),
    db: AsyncSession = Depends(get_db),
):
    return ConsentOverview(
        current=await consent_service.list_current(db, access.subject.id),
        history=await consent_service.list_history(db, access.subject.id),
    )


@router.post("/{user_id}/consents/{purpose}/grant", response_model=ConsentState)
async def grant_consent(
    purpose: ConsentPurpose,
    payload: ConsentGrantRequest,
    access: SubjectAccess = Depends(subject_access("consent_grant")),
    db: AsyncSession = Depends(get_db),
):
    change = await consent_service.grant(
        db, access.subject.id, purpose, payload.policy_version, payload.source
    )
    return _consent_state(purpose, change)


@router.post("/{user_id}/consents/{purpose}/revoke", response_model=ConsentState)
async def revoke_consent(
    purpose: ConsentPurpose,
    payload: ConsentRevokeRequest | None = None,
    access: SubjectAccess = Depends(subject_access("consent_revoke")),
    db: AsyncSession = Depends(get_db),
):
    source = payload.source if payload else "api"
    change = await consent_service.revoke(db, access.subject.id, purpose, source)
    return _consent_state(purpose, change)


@router.post("/{user_id}/marketing-email", status_code=202)
async def queue_marketing_email(
    payload: MarketingRequest,
    access: SubjectAccess = Depends(subject_access("marketing_email_request")),
    db: AsyncSession = Depends(get_db),
):
    message = await marketing_service.enqueue_marketing_email(
        db, access.subject.id, payload.campaign, access.actor.id, access.correlation_id
    )
    return {"decision": "ALLOW", "message_id": message.id, "status": message.status}


@router.post("/{user_id}/analytics-events", status_code=201)
async def track_analytics_event(
    payload: AnalyticsRequest,
    access: SubjectAccess = Depends(subject_access("analytics_event_request")),
    db: AsyncSession = Depends(get_db),
):
    event = await marketing_service.record_analytics_event(
        db, access.subject.id, payload.event_name, access.actor.id, access.correlation_id
    )
    return {"decision": "ALLOW", "event_id": event.id}


@admin_router.post("/dispatch", dependencies=[Depends(require_admin)])
async def dispatch_marketing(db: AsyncSession = Depends(get_db)):
    """Runs the background job on demand; consent is re-checked for every queued item."""
    return await marketing_service.dispatch_pending_marketing(db)
