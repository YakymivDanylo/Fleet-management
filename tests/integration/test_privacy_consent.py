"""Task 4: Consent Management Engine and Policy Gate."""

import pytest
from httpx import AsyncClient
from privacy_support import ALICE, BOB, create_account, create_admin, create_fleet
from sqlalchemy import func, select

from fleet_management.models import (
    AnalyticsEvent,
    ConsentHistory,
    ConsentPurpose,
    MarketingMessage,
    MarketingStatus,
)
from fleet_management.services import marketing_service
from fleet_management.services.consent_service import (
    CURRENT_POLICY_VERSION,
    ConsentPolicyGate,
)

MARKETING = "MARKETING_EMAIL"
ANALYTICS = "OPTIONAL_ANALYTICS"


@pytest.fixture
async def alice(client: AsyncClient):
    return await create_account(client, ALICE)


@pytest.fixture
async def bob(client: AsyncClient):
    return await create_account(client, BOB)


async def grant(client, account, purpose=MARKETING, version=CURRENT_POLICY_VERSION, source="web"):
    return await client.post(
        f"/api/users/{account.id}/consents/{purpose}/grant",
        json={"policy_version": version, "source": source},
        headers=account.headers,
    )


async def revoke(client, account, purpose=MARKETING):
    return await client.post(
        f"/api/users/{account.id}/consents/{purpose}/revoke", headers=account.headers
    )


async def send_marketing(client, account):
    return await client.post(
        f"/api/users/{account.id}/marketing-email",
        json={"campaign": "spring"},
        headers=account.headers,
    )


async def count(session_factory, model) -> int:
    async with session_factory() as db:
        return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def test_grant_allow_revoke_deny_scenario(client: AsyncClient, alice, session_factory):
    # initial state: DENY, no side effect
    denied = await send_marketing(client, alice)
    assert denied.status_code == 403
    assert denied.json() == {
        "decision": "DENY", "purpose": MARKETING, "reason": "no_consent_on_record",
    }  # fmt: skip
    assert await count(session_factory, MarketingMessage) == 0

    # GRANT -> ALLOW with an observable side effect
    assert (await grant(client, alice)).status_code == 200
    allowed = await send_marketing(client, alice)
    assert allowed.status_code == 202 and allowed.json()["decision"] == "ALLOW"
    assert await count(session_factory, MarketingMessage) == 1

    # REVOKE -> DENY again, side effect count unchanged
    assert (await revoke(client, alice)).status_code == 200
    blocked = await send_marketing(client, alice)
    assert blocked.status_code == 403 and blocked.json()["reason"] == "consent_withdrawn"
    assert await count(session_factory, MarketingMessage) == 1


async def test_consent_for_one_purpose_does_not_allow_another(
    client: AsyncClient, alice, session_factory
):
    await grant(client, alice, MARKETING)

    analytics = await client.post(
        f"/api/users/{alice.id}/analytics-events",
        json={"event_name": "page_view"},
        headers=alice.headers,
    )

    assert analytics.status_code == 403 and analytics.json()["purpose"] == ANALYTICS
    assert await count(session_factory, AnalyticsEvent) == 0
    await grant(client, alice, ANALYTICS)
    ok = await client.post(
        f"/api/users/{alice.id}/analytics-events",
        json={"event_name": "page_view"},
        headers=alice.headers,
    )
    assert ok.status_code == 201
    await revoke(client, alice, MARKETING)  # revoking one purpose leaves the other intact
    again = await client.post(
        f"/api/users/{alice.id}/analytics-events",
        json={"event_name": "page_view"},
        headers=alice.headers,
    )
    assert again.status_code == 201 and await count(session_factory, AnalyticsEvent) == 2


async def test_stale_policy_version_is_denied(client: AsyncClient, alice, session_factory):
    await grant(client, alice, version="2020-01")

    response = await send_marketing(client, alice)

    assert response.status_code == 403 and response.json()["reason"] == "policy_version_mismatch"
    assert await count(session_factory, MarketingMessage) == 0
    await grant(client, alice)  # accepting the current policy re-enables the action
    assert (await send_marketing(client, alice)).status_code == 202


async def test_grant_and_revoke_are_idempotent(client: AsyncClient, alice, session_factory):
    first = await grant(client, alice)
    second = await grant(client, alice)
    assert first.json()["changed"] is True and second.json()["changed"] is False
    assert await count(session_factory, ConsentHistory) == 1

    assert (await revoke(client, alice)).json()["changed"] is True
    repeated = await revoke(client, alice)
    assert repeated.status_code == 200 and repeated.json()["changed"] is False
    assert repeated.json()["status"] == "WITHDRAWN"
    assert await count(session_factory, ConsentHistory) == 2

    never = await revoke(client, alice, ANALYTICS)  # revoke without prior grant: no record created
    assert never.json()["status"] == "NONE" and never.json()["changed"] is False
    assert await count(session_factory, ConsentHistory) == 2


async def test_state_and_history_keep_evidence(client: AsyncClient, alice):
    await grant(client, alice, source="mobile_app")
    await revoke(client, alice)
    await grant(client, alice, version=CURRENT_POLICY_VERSION, source="web")

    overview = (await client.get(f"/api/users/{alice.id}/consents", headers=alice.headers)).json()

    current = overview["current"]
    assert len(current) == 1
    assert (
        current[0]["status"] == "GRANTED" and current[0]["policy_version"] == CURRENT_POLICY_VERSION
    )
    assert current[0]["source"] == "web"
    assert current[0]["granted_at"] and current[0]["withdrawn_at"] and current[0]["updated_at"]
    history = overview["history"]
    assert [h["action"] for h in history] == ["GRANT", "REVOKE", "GRANT"]
    assert [h["source"] for h in history] == ["mobile_app", "api", "web"]
    assert all(h["policy_version"] == CURRENT_POLICY_VERSION and h["occurred_at"] for h in history)


async def test_invalid_purpose_is_rejected(client: AsyncClient, alice):
    response = await client.post(
        f"/api/users/{alice.id}/consents/WORLD_DOMINATION/grant",
        json={"policy_version": "2026-01"},
        headers=alice.headers,
    )

    assert response.status_code == 422


async def test_stranger_cannot_manage_foreign_consent(
    client: AsyncClient, alice, bob, session_factory
):
    response = await client.post(
        f"/api/users/{alice.id}/consents/{MARKETING}/grant",
        json={"policy_version": "2026-01"},
        headers=bob.headers,
    )
    listing = await client.get(f"/api/users/{alice.id}/consents", headers=bob.headers)
    unauth = await client.post(
        f"/api/users/{alice.id}/consents/{MARKETING}/grant", json={"policy_version": "2026-01"}
    )

    assert response.status_code == 404 and listing.status_code == 404 and unauth.status_code == 401
    assert await count(session_factory, ConsentHistory) == 0


async def test_background_job_rechecks_consent_before_sending(
    client: AsyncClient, alice, session_factory
):
    await grant(client, alice)
    assert (await send_marketing(client, alice)).status_code == 202  # queued while consent is valid
    await revoke(client, alice)  # withdrawn after queueing, before the job runs

    async with session_factory() as db:
        counts = await marketing_service.dispatch_pending_marketing(db)

    assert counts == {"sent": 0, "skipped": 1}
    async with session_factory() as db:
        statuses = (await db.execute(select(MarketingMessage.status))).scalars().all()
    assert statuses == [MarketingStatus.SKIPPED]


async def test_background_job_sends_while_consent_holds(
    client: AsyncClient, alice, session_factory
):
    await grant(client, alice)
    await send_marketing(client, alice)

    async with session_factory() as db:
        counts = await marketing_service.dispatch_pending_marketing(db)

    assert counts == {"sent": 1, "skipped": 0}


async def test_gate_reads_fresh_state_each_call(client: AsyncClient, alice, session_factory):
    async with session_factory() as db:  # one long-lived session, state changes in between
        assert not (
            await ConsentPolicyGate.check(db, alice.id, ConsentPurpose.MARKETING_EMAIL)
        ).allowed
        await grant(client, alice)
        assert (await ConsentPolicyGate.check(db, alice.id, ConsentPurpose.MARKETING_EMAIL)).allowed
        await revoke(client, alice)
        decision = await ConsentPolicyGate.check(db, alice.id, ConsentPurpose.MARKETING_EMAIL)
        assert decision.label == "DENY" and decision.reason == "consent_withdrawn"


async def test_admin_dispatch_endpoint_requires_admin(client: AsyncClient, alice, session_factory):
    admin_headers = await create_admin(session_factory, client)

    assert (await client.post("/api/marketing/dispatch", headers=alice.headers)).status_code == 403
    ok = await client.post("/api/marketing/dispatch", headers=admin_headers)
    assert ok.status_code == 200 and ok.json() == {"sent": 0, "skipped": 0}


async def test_contract_functions_are_not_blocked_by_missing_consent(client: AsyncClient, alice):
    """Renting a car is a contractual/system function: it must work with zero consents."""
    _, vehicle_id = await create_fleet(client)
    renter = await client.post(
        f"/api/users/{alice.id}/renter-profile",
        json={"full_name": ALICE["full_name"], "license_number": ALICE["license"]},
        headers=alice.headers,
    )
    renter_id = renter.json()["renter_id"]

    rental = await client.post(
        "/rentals/start", json={"renter_id": renter_id, "vehicle_id": vehicle_id}
    )

    assert rental.status_code == 201
    consents = (await client.get(f"/api/users/{alice.id}/consents", headers=alice.headers)).json()
    assert consents == {"current": [], "history": []}
