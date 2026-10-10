"""Pure functions that mask PII and redact secrets in text and nested structures.

Policy (see docs/lab4-privacy-gdpr.md):
- secrets (password, token, api key, authorization, JWT, password hash) -> [REDACTED]
- email -> first character + *** + domain; phone -> +***<last two digits>
- name-like fields (full_name, license_number, ...) -> first character + ***
"""

import dataclasses
import re
from typing import Any

REDACTED = "[REDACTED]"

_SECRET_KEY = (
    r"[\w-]*(?:password|passwd|pwd|token|api[_-]?key|secret|authorization|credential)[\w-]*"
)
_NAME_KEYS = frozenset({"full_name", "first_name", "last_name", "license_number"})

_SECRET_KEY_RE = re.compile(_SECRET_KEY, re.IGNORECASE)
_SECRET_KV_RE = re.compile(
    rf"""(?P<key>{_SECRET_KEY})(?P<sep>["']?\s*[:=]\s*)"""
    r"""(?P<val>"[^"]*"|'[^']*'|(?:(?:Bearer|Basic)\s+)?[^\s,;}&\]]+)""",
    re.IGNORECASE,
)
_NAME_KV_RE = re.compile(
    r"""(?P<key>["']?(?:full_name|first_name|last_name|license_number)["']?\s*[:=]\s*)"""
    r"""(?P<q>["'])(?P<val>.*?)(?P=q)""",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
_HASH_RE = re.compile(r"\$argon2[\w$=,+/.-]+")
_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
_PHONE_RE = re.compile(r"(?<![\w+])\+?\d(?:[\s().-]?\d){8,14}(?!\w)")
_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def mask_email(email: str) -> str:
    return _EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", email)


def _mask_phone_match(match: re.Match[str]) -> str:
    raw = match.group(0)
    if _ISO_DATE_RE.match(raw):
        return raw
    digits = re.sub(r"\D", "", raw)
    prefix = "+" if raw.startswith("+") else ""
    return f"{prefix}***{digits[-2:]}"


def mask_phone(text: str) -> str:
    return _PHONE_RE.sub(_mask_phone_match, text)


def mask_name(value: str) -> str:
    return f"{value[0]}***" if value else value


def _redact_secret_kv(match: re.Match[str]) -> str:
    val = match.group("val")
    quote = val[0] if val[0] in "\"'" else ""
    return f"{match.group('key')}{match.group('sep')}{quote}{REDACTED}{quote}"


def _mask_name_kv(match: re.Match[str]) -> str:
    q = match.group("q")
    return f"{match.group('key')}{q}{mask_name(match.group('val'))}{q}"


def sanitize_text(text: str) -> str:
    text = _SECRET_KV_RE.sub(_redact_secret_kv, text)
    text = _BEARER_RE.sub(f"Bearer {REDACTED}", text)
    text = _JWT_RE.sub(REDACTED, text)
    text = _HASH_RE.sub(REDACTED, text)
    text = _NAME_KV_RE.sub(_mask_name_kv, text)
    text = mask_email(text)
    return mask_phone(text)


def _sanitize_item(key: str, value: Any) -> Any:
    if _SECRET_KEY_RE.fullmatch(key):
        return REDACTED
    if key.lower() in _NAME_KEYS and isinstance(value, str):
        return mask_name(value)
    return sanitize_value(value)


def sanitize_value(value: Any) -> Any:
    """Recursively sanitize dicts, sequences, pydantic models and dataclasses."""
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, dict):
        return {k: _sanitize_item(str(k), v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return type(value)(sanitize_value(v) for v in value)
    if hasattr(value, "model_dump"):
        return sanitize_value(value.model_dump())
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return sanitize_value(dataclasses.asdict(value))
    return value
