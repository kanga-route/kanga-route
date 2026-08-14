"""Product-neutral email address syntax and normalization helpers."""

import re

EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


def normalize_email_address(value: object) -> str:
    """Return a normalized address or raise ValueError without doing I/O."""
    if not isinstance(value, str):
        raise ValueError("email address must be a string")
    normalized = value.strip().lower()
    if (
        not normalized
        or len(normalized) > 254
        or EMAIL_REGEX.fullmatch(normalized) is None
    ):
        raise ValueError("email address syntax is invalid")
    return normalized
