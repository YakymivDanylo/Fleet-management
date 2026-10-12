import re
import uuid
from contextvars import ContextVar

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_VALID_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def accept_or_generate(incoming: str | None) -> str:
    """Reuse a well-formed client-supplied ID, otherwise generate one (log-injection guard)."""
    if incoming and _VALID_ID_RE.match(incoming):
        return incoming
    return new_correlation_id()


def current_correlation_id() -> str:
    return correlation_id_var.get() or new_correlation_id()
