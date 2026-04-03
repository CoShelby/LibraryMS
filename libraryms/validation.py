from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

_PHONE_PREFIXES = {"70", "71", "73", "77"}
_PHONE_CORE_RE = re.compile(r"^\d{9}$")


def normalize_contact_email(value: str) -> str:
    """Validate and normalize an email for member/admin contact usage."""
    normalized = (value or "").strip().lower()
    if not normalized:
        raise ValidationError("البريد الإلكتروني مطلوب.")

    try:
        validate_email(normalized)
    except ValidationError as exc:
        raise ValidationError("صيغة البريد الإلكتروني غير صحيحة.") from exc

    return normalized


def normalize_yemen_phone(value: str) -> str:
    """Accept local Yemeni mobile numbers and normalize to +967XXXXXXXXX."""
    raw = (value or "").strip().replace(" ", "").replace("-", "")
    if not raw:
        raise ValidationError("رقم الهاتف مطلوب.")

    if raw.startswith("+967"):
        core = raw[4:]
    elif raw.startswith("00967"):
        core = raw[5:]
    else:
        core = raw

    if not _PHONE_CORE_RE.match(core):
        raise ValidationError("رقم الهاتف يجب أن يتكون من 9 أرقام.")

    if core[:2] not in _PHONE_PREFIXES:
        raise ValidationError("رقم الهاتف يجب أن يبدأ بـ 70 أو 71 أو 73 أو 77.")

    return f"+967{core}"

