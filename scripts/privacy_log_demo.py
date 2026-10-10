"""Live demo for Lab 4, step 1: the same log calls before and after the sanitizing layer.

    python scripts/privacy_log_demo.py            # text logs
    LOG_FORMAT=json python scripts/privacy_log_demo.py

All values are synthetic.
"""

import io
import logging
import os

from fleet_management.privacy import install
from fleet_management.privacy.correlation import correlation_id_var

EMAIL = "alice.synthetic@example.com"
PHONE = "+380000000012"
PASSWORD = "S3cret-Passw0rd-Synthetic"  # gitleaks:allow
TOKEN = "tok_synthetic_0123456789abcdef"  # gitleaks:allow
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c3ludGhldGljLXNpZw"  # gitleaks:allow


def emit(logger: logging.Logger) -> None:
    """Deliberately careless logging: three formats, one nested payload, one exception."""
    logger.info("register email=%s phone=%s password=%s", EMAIL, PHONE, PASSWORD)
    logger.info(
        "payload=%s", {"user": {"email": EMAIL, "full_name": "Alice Synthetic"}, "token": TOKEN}
    )
    logger.warning(f"request failed, header Authorization: Bearer {JWT}")
    try:
        raise ValueError(f"cannot send to {EMAIL} ({PHONE}) api_key={TOKEN}")
    except ValueError:
        logger.exception(
            "delivery failed", extra={"operation": "send_welcome", "password": PASSWORD}
        )


def build(name: str, protected: bool) -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    if protected:
        install(handler, json_format=os.getenv("LOG_FORMAT", "text").lower() == "json")
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger = logging.getLogger(name)
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger, stream


def main() -> None:
    correlation_id_var.set("demo-corr-0001")
    for title, protected in (("BEFORE (no sanitizer)", False), ("AFTER (central sanitizer)", True)):
        logger, stream = build(f"demo.{protected}", protected)
        emit(logger)
        print(f"===== {title} =====")
        print(stream.getvalue())
        leaked = [v for v in (EMAIL, PHONE, PASSWORD, TOKEN, JWT) if v in stream.getvalue()]
        print(f"-> leaked sensitive values: {len(leaked)}\n")


if __name__ == "__main__":
    main()
