from __future__ import annotations

import re


SUBSCRIPTION_ACCESS_CODE_MIN_LENGTH = 4
SUBSCRIPTION_ACCESS_CODE_MAX_LENGTH = 12
ADMIN_ACCESS_CODE_MIN_LENGTH = 8
ADMIN_ACCESS_CODE_MAX_LENGTH = 64

ACCESS_CODE_RE = re.compile(rf"^[0-9]{{{SUBSCRIPTION_ACCESS_CODE_MIN_LENGTH},{SUBSCRIPTION_ACCESS_CODE_MAX_LENGTH}}}$")
ADMIN_ACCESS_CODE_RE = re.compile(rf"^[^\s\x00-\x1f\x7f]{{{ADMIN_ACCESS_CODE_MIN_LENGTH},{ADMIN_ACCESS_CODE_MAX_LENGTH}}}$")
BCRYPT_HASH_RE = re.compile(r"^\$(2a|2b|2y)\$(0[4-9]|[12][0-9]|3[01])\$[./A-Za-z0-9]{53}$")


def validate_access_code_shape(code: str) -> bool:
    return bool(ACCESS_CODE_RE.fullmatch(code))


def validate_access_code_hash_shape(access_code_hash: str) -> None:
    if not BCRYPT_HASH_RE.fullmatch(access_code_hash):
        raise ValueError("access_code_hash must be a valid bcrypt hash with $2a$, $2b$, or $2y$ prefix")


def bcrypt_hash_for_verify(access_code_hash: str) -> str:
    validate_access_code_hash_shape(access_code_hash)
    if access_code_hash.startswith("$2y$"):
        return "$2a$" + access_code_hash[4:]
    return access_code_hash


def verify_access_code(code: str, access_code_hash: str) -> bool:
    if not validate_access_code_shape(code):
        return False
    candidate_hash = bcrypt_hash_for_verify(access_code_hash)
    try:
        import bcrypt
    except ImportError as exc:
        raise RuntimeError("bcrypt is required for access_code authentication") from exc
    return bool(bcrypt.checkpw(code.encode("ascii"), candidate_hash.encode("ascii")))
