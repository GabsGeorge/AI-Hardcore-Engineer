"""Argon2id with a per-deployment pepper and a local breach list.

The pepper is a server-side secret concatenated to every password before hashing. A dump of
the DB alone is not enough to brute-force: the attacker also needs ``PASSWORD_PEPPER``.
The breach list is a text file shipped with the image: one SHA-1 prefix per line (first 10
chars, uppercase) — never the password in clear."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings
from app.observability.logging import get_logger

_PWNED_FILE = Path(__file__).resolve().parents[1] / "auth_data" / "pwned_sha1_prefixes.txt"
MIN_LENGTH = 12


@lru_cache(maxsize=1)
def _hasher() -> PasswordHasher:
    # OWASP 2024 recommendation for argon2id.
    return PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4, hash_len=32)


@lru_cache(maxsize=1)
def _breach_prefixes() -> frozenset[str]:
    try:
        text = _PWNED_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        get_logger().warning("pwned_list_missing", path=str(_PWNED_FILE))
        return frozenset()
    out: set[str] = set()
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.add(s.upper())
    return frozenset(out)


class WeakPasswordError(ValueError):
    """Raised when a password fails length or breach-list checks."""


def _peppered(raw: str) -> str:
    pepper = get_settings().password_pepper
    secret = pepper.get_secret_value() if pepper is not None else ""
    return f"{raw}\x00{secret}"


def _is_pwned(raw: str) -> bool:
    prefixes = _breach_prefixes()
    if not prefixes:
        return False
    digest = hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    return digest[:10] in prefixes


def check_strength(raw: str) -> None:
    """Enforce the only two rules the spec declares (FR-003): length and breach list."""
    if len(raw) < MIN_LENGTH:
        raise WeakPasswordError("too_short")
    if _is_pwned(raw):
        raise WeakPasswordError("breached")


def hash_password(raw: str) -> str:
    check_strength(raw)
    return str(_hasher().hash(_peppered(raw)))


def verify_password(stored: str, raw: str) -> bool:
    """Constant-time check; a hash from a different parameter set still verifies, so we rotate
    silently when the recommendation changes (``needs_rehash``)."""
    try:
        return bool(_hasher().verify(stored, _peppered(raw)))
    except VerifyMismatchError:
        return False
    except Exception:  # noqa: BLE001 — malformed hash or lib mismatch; fail closed, no leak
        return False


def needs_rehash(stored: str) -> bool:
    try:
        return bool(_hasher().check_needs_rehash(stored))
    except Exception:  # noqa: BLE001 — any error forces a rehash on next login
        return True
