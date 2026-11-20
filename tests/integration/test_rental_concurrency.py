"""RFC-001 / ADR-0005: two renters racing for the last available vehicle get exactly one rental."""

import asyncio

from sqlalchemy import func, select

from fleet_management.exceptions import VehicleNotAvailableError
from fleet_management.models import Rental, RentalStatus, Renter, Station, Vehicle
from fleet_management.services import rental_service

BARRIER_TIMEOUT_S = 0.5


async def seed(session_factory) -> tuple[int, int, int]:
    async with session_factory() as db:
        station = Station(address="Race st. 1", capacity=5)
        db.add(station)
        await db.flush()
        vehicle = Vehicle(license_plate="RACE-001", model="Leaf", station_id=station.id)
        first = Renter(full_name="First", license_number="RACE-A")
        second = Renter(full_name="Second", license_number="RACE-B")
        db.add_all([vehicle, first, second])
        await db.commit()
        return vehicle.id, first.id, second.id


class InterleavedSession:
    """Session proxy: after reading the vehicle, wait until the rival transaction has read it too.

    This forces the classic check-then-act interleaving (both see ``available``). With a row lock
    the rival's read blocks instead, the barrier times out and the transactions serialize.
    """

    def __init__(self, session, arrived: asyncio.Barrier):
        self._session, self._arrived = session, arrived

    def __getattr__(self, name):
        return getattr(self._session, name)

    async def get(self, entity, ident, **kwargs):
        obj = await self._session.get(entity, ident, **kwargs)
        if entity is Vehicle:
            try:
                await asyncio.wait_for(self._arrived.wait(), BARRIER_TIMEOUT_S)
            except TimeoutError:
                pass
        return obj


async def attempt(session_factory, barrier, renter_id: int, vehicle_id: int) -> str:
    async with session_factory() as session:
        try:
            await rental_service.start_rental(
                InterleavedSession(session, barrier), renter_id, vehicle_id
            )
        except VehicleNotAvailableError:
            return "409"
        return "201"


async def test_race_for_last_vehicle_creates_exactly_one_active_rental(session_factory):
    vehicle_id, first, second = await seed(session_factory)
    barrier = asyncio.Barrier(2)

    results = await asyncio.gather(
        attempt(session_factory, barrier, first, vehicle_id),
        attempt(session_factory, barrier, second, vehicle_id),
    )

    async with session_factory() as db:
        active = await db.scalar(
            select(func.count())
            .select_from(Rental)
            .where(Rental.vehicle_id == vehicle_id, Rental.status == RentalStatus.ACTIVE)
        )
    assert sorted(results) == ["201", "409"]
    assert active == 1
