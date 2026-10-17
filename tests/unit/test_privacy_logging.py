"""Task 1: central log sanitization. All values below are synthetic."""

import io
import json
import logging
from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from fleet_management.privacy import install
from fleet_management.privacy.correlation import correlation_id_var

EMAIL = "alice.synthetic@example.com"
PHONE = "+380000000012"
PHONE_DIGITS = "380000000012"
PASSWORD = "S3cret-Passw0rd-Synthetic"  # gitleaks:allow
TOKEN = "tok_synthetic_0123456789abcdef"  # gitleaks:allow
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c3ludGhldGljLXNpZw"  # gitleaks:allow
FULL_NAME = "Alice Synthetic"

SENSITIVE = [EMAIL, PHONE, PHONE_DIGITS, PASSWORD, TOKEN, JWT, FULL_NAME]


class SignupDto(BaseModel):
    email: str
    password: str
    full_name: str


class Envelope(BaseModel):
    request_id: str
    payload: SignupDto


@dataclass
class ProfileDto:
    contact: dict
    api_key: str


@pytest.fixture
def capture():
    def build(json_format: bool = False):
        stream = io.StringIO()
        handler = install(logging.StreamHandler(stream), json_format=json_format)
        logger = logging.getLogger(f"test.privacy.{id(stream)}")
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)
        return logger, stream

    return build


def assert_no_leak(output: str) -> None:
    leaked = [value for value in SENSITIVE if value in output]
    assert not leaked, f"sensitive values leaked into the log: {leaked}\n{output}"


def test_plain_text_masks_pii_and_redacts_secrets(capture):
    logger, stream = capture()

    logger.info("signup email=%s phone=%s password=%s token=%s", EMAIL, PHONE, PASSWORD, TOKEN)

    output = stream.getvalue()
    assert_no_leak(output)
    assert "a***@example.com" in output
    assert "+***12" in output
    assert "password=[REDACTED]" in output
    assert "token=[REDACTED]" in output


def test_fstring_message_and_bearer_header(capture):
    logger, stream = capture()

    logger.warning(f"auth failed for {EMAIL}; Authorization: Bearer {JWT}; call {PHONE}")

    output = stream.getvalue()
    assert_no_leak(output)
    assert "Authorization: [REDACTED]" in output


def test_standalone_bearer_token_and_jwt_are_redacted(capture):
    logger, stream = capture()

    logger.info("forwarding Bearer %s and raw %s", JWT, JWT)

    output = stream.getvalue()
    assert_no_leak(output)
    assert "Bearer [REDACTED]" in output


def test_nested_dto_in_args_is_sanitized(capture):
    logger, stream = capture()
    dto = Envelope(
        request_id="req-1",
        payload=SignupDto(email=EMAIL, password=PASSWORD, full_name=FULL_NAME),
    )

    logger.info("received %s", dto)
    logger.info("received %s", dto.model_dump())
    logger.info("received %s", ProfileDto(contact={"phone": PHONE}, api_key=TOKEN))

    output = stream.getvalue()
    assert_no_leak(output)
    assert "req-1" in output  # diagnostic data survives


def test_dto_repr_in_plain_string_is_sanitized(capture):
    logger, stream = capture()
    dto = SignupDto(email=EMAIL, password=PASSWORD, full_name=FULL_NAME)

    logger.info(f"payload={dto!r} serialized={dto.model_dump_json()}")

    assert_no_leak(stream.getvalue())


def test_exception_message_and_traceback_are_sanitized(capture):
    logger, stream = capture()

    try:
        raise ValueError(f"cannot deliver to {EMAIL} ({PHONE}) using password={PASSWORD}")
    except ValueError:
        logger.exception("delivery failed")

    output = stream.getvalue()
    assert_no_leak(output)
    assert "ValueError" in output  # exception type is still diagnosable
    assert "Traceback" in output


def test_extra_fields_are_sanitized(capture):
    logger, stream = capture(json_format=True)

    logger.info("login", extra={"email": EMAIL, "password": PASSWORD, "operation": "login"})

    record = json.loads(stream.getvalue())
    assert_no_leak(stream.getvalue())
    assert record["password"] == "[REDACTED]"
    assert record["operation"] == "login"


def test_json_log_stays_valid_and_keeps_diagnostics(capture):
    logger, stream = capture(json_format=True)
    token = correlation_id_var.set("corr-abc-123")
    try:
        logger.info("payload=%s", {"user": {"email": EMAIL, "token": TOKEN}, "op": "export"})
        try:
            raise RuntimeError(f"boom {EMAIL}")
        except RuntimeError:
            logger.exception("failed")
    finally:
        correlation_id_var.reset(token)

    lines = stream.getvalue().strip().splitlines()
    records = [json.loads(line) for line in lines]  # every line must be valid JSON
    assert all(r["correlation_id"] == "corr-abc-123" for r in records)
    assert records[0]["level"] == "INFO"
    assert "export" in records[0]["message"]
    assert "RuntimeError" in records[1]["exception"]
    assert_no_leak(stream.getvalue())


def test_json_embedded_in_message_is_sanitized(capture):
    logger, stream = capture()

    logger.info(
        'body={"email": "%s", "password": "%s", "full_name": "%s"}', EMAIL, PASSWORD, FULL_NAME
    )

    assert_no_leak(stream.getvalue())


def test_text_format_keeps_correlation_id_and_operation(capture):
    logger, stream = capture()
    token = correlation_id_var.set("corr-xyz-789")
    try:
        logger.info("operation=export_personal_data subject=user:42 result=ok")
    finally:
        correlation_id_var.reset(token)

    output = stream.getvalue()
    assert "[corr-xyz-789]" in output
    assert "operation=export_personal_data subject=user:42 result=ok" in output


def test_non_pii_numbers_and_dates_are_not_destroyed(capture):
    logger, stream = capture()

    logger.info("rental=%d cost=%.2f at 2026-10-10 10:00 status=ok", 15, 20.0)

    assert "rental=15 cost=20.00 at 2026-10-10 10:00 status=ok" in stream.getvalue()


def test_negative_control_unprotected_logger_does_leak():
    """Proves the leak detector works: without the sanitizer the same call must fail it."""
    stream = io.StringIO()
    logger = logging.getLogger("test.privacy.unprotected")
    logger.handlers = [logging.StreamHandler(stream)]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    logger.info("email=%s password=%s", EMAIL, PASSWORD)

    with pytest.raises(AssertionError):
        assert_no_leak(stream.getvalue())


def test_exception_object_in_args_and_extra_keeps_repr_but_masks_pii(capture):
    logger, stream = capture(json_format=True)

    logger.warning(
        "failed: %r", RuntimeError(f"smtp rejected {EMAIL}"), extra={"error": ValueError(PHONE)}
    )

    output = stream.getvalue()
    assert_no_leak(output)
    assert "RuntimeError" in output
