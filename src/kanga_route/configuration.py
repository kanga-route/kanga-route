"""Shared runtime configuration validation."""

import os


def validate_smtp_identity() -> None:
    """Reject placeholder or malformed SMTP identities before probing."""
    helo_domain = os.getenv(
        "SMTP_HELO_DOMAIN", "verifier.example.invalid"
    ).strip().lower().rstrip(".")
    from_email = os.getenv(
        "SMTP_MAIL_FROM", "verify@example.invalid"
    ).strip().lower()
    from_local, separator, from_domain = from_email.rpartition("@")

    if (
        not helo_domain
        or helo_domain.endswith(".invalid")
        or "." not in helo_domain
        or any(character.isspace() for character in helo_domain)
    ):
        raise ValueError(
            "SMTP_HELO_DOMAIN must be a configured public hostname"
        )
    if (
        separator != "@"
        or from_email.count("@") != 1
        or not from_local
        or not from_domain
        or "." not in from_domain
        or from_domain.endswith(".invalid")
        or any(character.isspace() for character in from_email)
    ):
        raise ValueError(
            "SMTP_MAIL_FROM must be a configured sender address"
        )
