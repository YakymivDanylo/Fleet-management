"""Lab 7 crash-test: uncontrolled mutation of M-class data in dispatch_pending_marketing.

The dispatcher rewrites ORM rows (``message.status``, ``message.processed_at``) and the
``counts`` accumulator while it is still deciding. Both tests describe what an immutable
implementation guarantees; against the mutable baseline they FAIL.
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from fleet_management.models import MarketingStatus
from fleet_management.services import marketing_service
from fleet_management.services.consent_service import ConsentPolicyGate, GateDecision
from fleet_management.services.marketing_service import DispatchOutcome

ALLOW = GateDecision(True, "granted")
DENY = GateDecision(False, "consent_withdrawn")


def _message(user_id: int) -> MagicMock:
    return MagicMock(user_id=user_id, status=MarketingStatus.QUEUED, processed_at=None)


def _session(*messages: MagicMock) -> MagicMock:
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = list(messages)
    db = MagicMock()
    db.execute = AsyncMock(return_value=rows)
    db.commit = AsyncMock()
    return db


async def test_gate_failure_midway_must_not_leave_phantom_sent_messages(monkeypatch):
    """Gate answers ALLOW for message 1, then crashes on message 2.

    Nothing was committed, so message 1 must still be QUEUED. The mutable loop has
    already overwritten its status to SENT: a phantom "sent" mail that was never sent.
    """
    first, second = _message(1), _message(2)
    gate = AsyncMock(side_effect=[ALLOW, RuntimeError("consent store unavailable")])
    monkeypatch.setattr(ConsentPolicyGate, "check", gate)
    db = _session(first, second)

    with pytest.raises(RuntimeError):
        await marketing_service.dispatch_pending_marketing(db)

    db.commit.assert_not_awaited()
    assert first.status == MarketingStatus.QUEUED, "message 1 was mutated to SENT before commit"
    assert first.processed_at is None


async def test_one_batch_shares_one_immutable_processed_at(monkeypatch):
    """Every message of one dispatch run must carry the same processed_at instant.

    The mutable loop re-reads the clock for each row, so the audit trail of a single run
    drifts: rows of one batch claim different processing times.
    """
    ticks = iter(datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=n) for n in range(10))

    class TickingClock:
        @staticmethod
        def now(_tz=None):
            return next(ticks)

    monkeypatch.setattr(marketing_service, "datetime", TickingClock)
    monkeypatch.setattr(ConsentPolicyGate, "check", AsyncMock(side_effect=[ALLOW, DENY, ALLOW]))
    messages = [_message(1), _message(2), _message(3)]

    counts = await marketing_service.dispatch_pending_marketing(_session(*messages))

    assert counts == {"sent": 2, "skipped": 1}
    assert len({m.processed_at for m in messages}) == 1, "processed_at drifted inside one batch"


@pytest.mark.parametrize(
    ("allowed", "status"),
    [(True, MarketingStatus.SENT), (False, MarketingStatus.SKIPPED)],
)
def test_outcome_is_an_immutable_value_object(allowed, status):
    moment = datetime(2026, 1, 1, tzinfo=UTC)
    message = _message(1)
    outcome = DispatchOutcome(message, allowed, moment)

    assert outcome.status == status
    with pytest.raises(FrozenInstanceError):
        outcome.allowed = not allowed
    with pytest.raises(FrozenInstanceError):
        outcome.processed_at = moment + timedelta(days=1)
    assert message.status == MarketingStatus.QUEUED, "deciding must not touch the row"

    outcome.apply()

    assert (message.status, message.processed_at) == (status, moment)
