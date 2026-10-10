"""Task 2: Right of Access / Personal Data Export."""

import io
import json
import logging

import pytest
from httpx import AsyncClient
from privacy_support import (
    ALICE,
    BOB,
    PASSWORD,
    create_account,
    create_admin,
    create_fleet,
    seed_full_profile,
)
from sqlalchemy import select

from fleet_management.models import AuditEvent, User
from fleet_management.privacy import install

FORBIDDEN_KEYS = ("hashed_password", "password", "token", "secret", "jwt")


@pytest.fixture
async def world(client: AsyncClient, session_factory):
    alice = await create_account(client, ALICE)
    bob = await create_account(client, BOB)
    _, vehicle_id = await create_fleet(client)
    await seed_full_profile(client, alice, vehicle_id)
    return alice, bob


def _all_keys(node) -> list[str]:
    if isinstance(node, dict):
        return [*node, *(k for value in node.values() for k in _all_keys(value))]
    if isinstance(node, list):
        return [k for item in node for k in _all_keys(item)]
    return []


async def export(client: AsyncClient, subject_id: int, headers: dict | None):
    return await client.get(f"/api/users/{subject_id}/personal-data", headers=headers or {})


async def test_owner_export_contains_every_source(client: AsyncClient, world):
    alice, _ = world

    response = await export(client, alice.id, alice.headers)

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["generated_at"].endswith("Z")
    assert body["subject_id"] == alice.id
    assert set(body["data_categories"]) >= {
        "profile",
        "settings",
        "activity",
        "rentals",
        "consents",
    }
    assert body["profile"]["email"] == ALICE["email"]
    assert body["profile"]["full_name"] == ALICE["full_name"]
    assert body["profile"]["phone"] == ALICE["phone"]
    assert body["settings"] == {"role": "user", "is_active": True, "anonymized": False}
    assert body["renter_profile"]["license_number"] == ALICE["license"]
    assert [a["action"] for a in body["activity"]] == ["login"]
    assert body["activity"][0]["ip_address"] and body["activity"][0]["user_agent"]
    assert len(body["rentals"]) == 1 and body["rentals"][0]["status"] == "active"
    assert {c["purpose"] for c in body["consents"]["current"]} == {
        "MARKETING_EMAIL",
        "OPTIONAL_ANALYTICS",
    }
    assert [h["action"] for h in body["consents"]["history"]] == ["GRANT", "GRANT"]
    assert body["consents"]["history"][0]["source"] == "web"
    assert [m["campaign"] for m in body["marketing_messages"]] == ["spring"]
    assert [e["event_name"] for e in body["analytics_events"]] == ["page_view"]
    assert {o["category"] for o in body["omissions"]} >= {"credentials", "telemetry"}


async def test_export_never_contains_forbidden_or_foreign_data(
    client: AsyncClient, world, session_factory
):
    alice, bob = world
    async with session_factory() as db:
        stored_hash = (await db.get(User, alice.id)).hashed_password

    response = await export(client, alice.id, alice.headers)
    raw = response.text

    keys = {key.lower() for key in _all_keys(response.json())}
    for forbidden in FORBIDDEN_KEYS:
        assert not [k for k in keys if forbidden in k], f"forbidden key {forbidden} in export"
    assert stored_hash not in raw and "$argon2" not in raw
    assert PASSWORD not in raw
    assert alice.headers["Authorization"].split()[1] not in raw
    for foreign in (BOB["email"], BOB["phone"], BOB["full_name"], BOB["license"]):
        assert foreign not in raw


async def test_export_has_stable_schema_for_user_without_data(client: AsyncClient):
    carol = await create_account(
        client,
        {
            "email": "carol.synthetic@example.com",
            "full_name": "Carol Synthetic",
            "phone": "+380000000056",
            "license": "-",
        },
    )

    body = (await export(client, carol.id, carol.headers)).json()

    assert body["renter_profile"] is None
    assert body["rentals"] == [] and body["marketing_messages"] == []
    assert body["analytics_events"] == []
    assert body["consents"] == {"current": [], "history": []}
    assert set(body) == {
        "schema_version", "generated_at", "subject_id", "data_categories", "profile", "settings",
        "renter_profile", "activity", "rentals", "consents", "marketing_messages",
        "analytics_events", "omissions",
    }  # fmt: skip


async def test_stranger_gets_404_without_data(client: AsyncClient, world):
    alice, bob = world

    response = await export(client, alice.id, bob.headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}
    assert ALICE["email"] not in response.text and ALICE["full_name"] not in response.text


async def test_nonexistent_subject_is_indistinguishable_from_foreign_one(
    client: AsyncClient, world, session_factory
):
    alice, bob = world
    admin_headers = await create_admin(session_factory, client)

    foreign = await export(client, alice.id, bob.headers)
    missing_for_user = await export(client, 99999, bob.headers)
    missing_for_admin = await export(client, 99999, admin_headers)

    assert foreign.status_code == missing_for_user.status_code == 404
    assert foreign.json() == missing_for_user.json() == missing_for_admin.json()


async def test_unauthenticated_is_401(client: AsyncClient, world):
    alice, _ = world

    assert (await export(client, alice.id, None)).status_code == 401
    bad = {"Authorization": "Bearer not-a-real-token"}
    assert (await export(client, alice.id, bad)).status_code == 401


async def test_admin_may_export_any_subject(client: AsyncClient, world, session_factory):
    alice, _ = world
    admin_headers = await create_admin(session_factory, client)

    response = await export(client, alice.id, admin_headers)

    assert response.status_code == 200
    assert response.json()["profile"]["email"] == ALICE["email"]


async def test_audit_events_record_ids_and_results_only(
    client: AsyncClient, world, session_factory
):
    alice, bob = world
    await export(client, alice.id, alice.headers)
    await export(client, alice.id, bob.headers)

    async with session_factory() as db:
        events = (
            (
                await db.execute(
                    select(AuditEvent)
                    .where(AuditEvent.event_type == "personal_data_export")
                    .order_by(AuditEvent.id)
                )
            )
            .scalars()
            .all()
        )

    assert [(e.actor_id, e.subject_id, e.result) for e in events] == [
        (alice.id, alice.id, "ok"),
        (bob.id, alice.id, "denied"),
    ]
    assert all(e.correlation_id for e in events)


async def test_export_does_not_leak_pii_or_payload_into_logs(client: AsyncClient, world):
    alice, bob = world
    raw_stream, safe_stream = io.StringIO(), io.StringIO()
    raw_handler = logging.StreamHandler(raw_stream)  # no sanitizer: shows what the app emits
    safe_handler = install(logging.StreamHandler(safe_stream))
    root = logging.getLogger()
    old_level = root.level
    root.setLevel(logging.DEBUG)
    root.addHandler(raw_handler)
    root.addHandler(safe_handler)
    try:
        await export(client, alice.id, alice.headers)
        await export(client, alice.id, bob.headers)
    finally:
        root.removeHandler(raw_handler)
        root.removeHandler(safe_handler)
        root.setLevel(old_level)

    for output in (raw_stream.getvalue(), safe_stream.getvalue()):
        for value in (
            ALICE["email"],
            ALICE["phone"],
            ALICE["full_name"],
            ALICE["license"],
            BOB["email"],
        ):
            assert value not in output
        assert '"profile"' not in output and "schema_version" not in output
    assert "personal_data_export" in safe_stream.getvalue()
    assert f"actor=user:{alice.id} subject=user:{alice.id} result=ok" in safe_stream.getvalue()


async def test_correlation_id_is_echoed_and_stored(client: AsyncClient, world, session_factory):
    alice, _ = world

    response = await client.get(
        f"/api/users/{alice.id}/personal-data",
        headers={**alice.headers, "X-Correlation-ID": "corr-test-0001"},
    )

    assert response.headers["X-Correlation-ID"] == "corr-test-0001"
    async with session_factory() as db:
        stored = (
            (
                await db.execute(
                    select(AuditEvent.correlation_id).where(
                        AuditEvent.event_type == "personal_data_export"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert stored == ["corr-test-0001"]
    assert json.loads(response.text)["subject_id"] == alice.id
