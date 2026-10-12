"""Task 3: Right to Erasure / anonymization workflow."""

import pytest
from httpx import AsyncClient
from privacy_support import (
    ALICE,
    BOB,
    PASSWORD,
    create_account,
    create_admin,
    create_fleet,
    scan_all_text_columns,
    seed_full_profile,
    table_counts,
)
from sqlalchemy import func, select, text

from fleet_management.models import AuditEvent, ConsentHistory, Rental, Renter, User
from fleet_management.services import erasure_service

ALICE_NEEDLES = ["alice.synthetic", "Alice Synthetic", "380000000012", "SYN-LIC-ALICE"]
OTHER_TABLES_UNCHANGED = ("vehicles", "stations", "telemetry_readings")


@pytest.fixture
async def world(client: AsyncClient):
    alice = await create_account(client, ALICE)
    bob = await create_account(client, BOB)
    _, vehicle_id = await create_fleet(client)
    rental_id = await seed_full_profile(client, alice, vehicle_id)
    return alice, bob, rental_id


async def anonymize(client: AsyncClient, subject_id: int, headers: dict | None):
    return await client.post(f"/api/users/{subject_id}/anonymize", headers=headers or {})


async def test_anonymize_removes_pii_from_every_source(client: AsyncClient, world, session_factory):
    alice, _, _ = world
    assert await scan_all_text_columns(session_factory, ALICE_NEEDLES)  # PII is there before

    response = await anonymize(client, alice.id, alice.headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "anonymized"
    assert body["actions"] == {
        "renters_anonymized": 1,
        "activity_deleted": 1,
        "marketing_messages_deleted": 1,
        "analytics_events_deleted": 1,
        "consents_withdrawn": 2,
    }
    assert await scan_all_text_columns(session_factory, ALICE_NEEDLES) == []
    async with session_factory() as db:
        user = await db.get(User, alice.id)
        assert user.email.startswith("anon-") and user.email.endswith("@anon.invalid")
        assert user.full_name == "Anonymized User" and user.phone is None
        assert user.is_active is False and user.anonymized_at is not None
        assert user.hashed_password.startswith("$argon2")  # valid but random: unusable


async def test_business_records_survive_with_intact_references(
    client: AsyncClient, world, session_factory
):
    alice, _, rental_id = world

    await anonymize(client, alice.id, alice.headers)

    async with session_factory() as db:
        rental = await db.get(Rental, rental_id)
        renter = await db.get(Renter, rental.renter_id)
        assert renter.user_id == alice.id and renter.full_name == "Anonymized User"
        orphans = (
            await db.execute(
                text(
                    "SELECT count(*) FROM rentals r LEFT JOIN renters p ON p.id = r.renter_id "
                    "LEFT JOIN vehicles v ON v.id = r.vehicle_id WHERE p.id IS NULL OR v.id IS NULL"
                )
            )
        ).scalar_one()
        assert orphans == 0
        assert (
            await db.execute(select(func.count(ConsentHistory.id)))
        ).scalar_one() == 4  # 2 GRANT + 2 REVOKE
    summary = await client.get("/rentals/summary")
    assert summary.status_code == 200 and summary.json()["active"] == 1


async def test_other_users_are_untouched(client: AsyncClient, world, session_factory):
    alice, bob, _ = world

    await anonymize(client, alice.id, alice.headers)

    async with session_factory() as db:
        other = await db.get(User, bob.id)
        assert other.email == BOB["email"] and other.phone == BOB["phone"]
        assert other.anonymized_at is None and other.is_active


async def test_second_run_is_idempotent(client: AsyncClient, world, session_factory):
    alice, _, _ = world
    admin_headers = await create_admin(session_factory, client)
    first = await anonymize(client, alice.id, alice.headers)
    before = await table_counts(session_factory)
    async with session_factory() as db:
        snapshot = (await db.get(User, alice.id)).email

    # The subject's own token is no longer valid; an admin repeats the request.
    again = await anonymize(client, alice.id, admin_headers)

    assert first.status_code == again.status_code == 200
    assert again.json()["status"] == "already_anonymized"
    assert again.json()["anonymized_at"] == first.json()["anonymized_at"]
    after = await table_counts(session_factory)
    assert {t: c for t, c in after.items() if t != "audit_events"} == {
        t: c for t, c in before.items() if t != "audit_events"
    }
    assert after["audit_events"] == before["audit_events"] + 1  # only an audit entry is added
    async with session_factory() as db:
        assert (await db.get(User, alice.id)).email == snapshot  # identifiers are not re-randomized
    assert await scan_all_text_columns(session_factory, ALICE_NEEDLES) == []


async def test_stranger_is_denied_and_nothing_changes(client: AsyncClient, world, session_factory):
    alice, bob, _ = world
    before = await table_counts(session_factory)

    response = await anonymize(client, alice.id, bob.headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}
    after = await table_counts(session_factory)
    assert {t: c for t, c in after.items() if t != "audit_events"} == {
        t: c for t, c in before.items() if t != "audit_events"
    }
    async with session_factory() as db:
        assert (await db.get(User, alice.id)).email == ALICE["email"]


async def test_unauthenticated_and_get_are_rejected(client: AsyncClient, world):
    alice, _, _ = world

    assert (await anonymize(client, alice.id, None)).status_code == 401
    assert (
        await client.get(f"/api/users/{alice.id}/anonymize", headers=alice.headers)
    ).status_code == 405


async def test_anonymized_account_cannot_log_in_or_reuse_token(client: AsyncClient, world):
    alice, _, _ = world
    await anonymize(client, alice.id, alice.headers)

    login = await client.post(
        "/auth/login", data={"username": ALICE["email"], "password": PASSWORD}
    )
    old_token = await client.get("/auth/me", headers=alice.headers)

    assert login.status_code == 401
    assert old_token.status_code == 401


async def test_failure_midway_rolls_everything_back(
    client: AsyncClient, world, session_factory, monkeypatch
):
    alice, _, _ = world
    before = await table_counts(session_factory)

    async def broken_step(db, user_id):
        raise RuntimeError("simulated failure after the user row was already modified")

    monkeypatch.setattr(erasure_service, "_anonymize_renters", broken_step)
    async with session_factory() as db:
        actor = await db.get(User, alice.id)
        with pytest.raises(RuntimeError):
            await erasure_service.anonymize_user(db, alice.id, actor, "corr-rollback")

    assert await table_counts(session_factory) == before
    assert await scan_all_text_columns(session_factory, ALICE_NEEDLES)  # PII still fully intact
    async with session_factory() as db:
        user = await db.get(User, alice.id)
        assert user.anonymized_at is None and user.is_active is True


async def test_audit_event_has_no_pii(client: AsyncClient, world, session_factory):
    alice, _, _ = world

    await anonymize(client, alice.id, alice.headers)

    async with session_factory() as db:
        events = (
            (await db.execute(select(AuditEvent).where(AuditEvent.event_type == "user_anonymize")))
            .scalars()
            .all()
        )
    assert [(e.actor_id, e.subject_id, e.result) for e in events] == [
        (alice.id, alice.id, "anonymized")
    ]
    assert events[0].correlation_id and events[0].occurred_at
    assert await scan_all_text_columns(session_factory, ALICE_NEEDLES) == []
