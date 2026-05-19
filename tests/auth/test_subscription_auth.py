import json
import time

import pytest

from dashbox.auth.access_code import validate_access_code_hash_shape, validate_access_code_shape
from dashbox.auth.cooldown_limiter import CooldownLimiter
from dashbox.auth.failure_limiter import FailureLimiter
from dashbox.auth.tokens import issue_access_token, validate_access_token
from dashbox.config import load_config


BCRYPT_HASH = "$2b$12$012345678901234567890u0123456789012345678901234567890"


def test_access_code_shape_requires_4_to_12_digits() -> None:
    assert validate_access_code_shape("1234")
    assert validate_access_code_shape("123456789012")
    assert not validate_access_code_shape("123")
    assert not validate_access_code_shape("1234567890123")
    assert not validate_access_code_shape("12ab")


def test_bcrypt_hash_shape_allows_supported_prefixes() -> None:
    validate_access_code_hash_shape(BCRYPT_HASH)
    validate_access_code_hash_shape("$2a$12$012345678901234567890u0123456789012345678901234567890")
    validate_access_code_hash_shape("$2y$12$012345678901234567890u0123456789012345678901234567890")

    with pytest.raises(ValueError, match="bcrypt"):
        validate_access_code_hash_shape("$2x$12$012345678901234567890u0123456789012345678901234567890")


def test_access_token_binds_subscription_audience_hash_and_expiry() -> None:
    secret = b"test-secret"
    token, expires_at = issue_access_token(
        secret=secret,
        sub_id="main",
        audience="tvbox",
        access_code_hash=BCRYPT_HASH,
        now=100,
        ttl_seconds=60,
    )

    assert expires_at == 160
    assert validate_access_token(token, secret=secret, sub_id="main", audience="tvbox", access_code_hash=BCRYPT_HASH, now=120)
    assert not validate_access_token(token, secret=secret, sub_id="alt", audience="tvbox", access_code_hash=BCRYPT_HASH, now=120)
    assert not validate_access_token(token, secret=secret, sub_id="main", audience="kodi", access_code_hash=BCRYPT_HASH, now=120)
    assert not validate_access_token(token, secret=secret, sub_id="main", audience="tvbox", access_code_hash=BCRYPT_HASH.replace("0", "1", 1), now=120)
    assert not validate_access_token(token, secret=secret, sub_id="main", audience="tvbox", access_code_hash=BCRYPT_HASH, now=160)


def test_access_token_accepts_dotted_subscription_id() -> None:
    secret = b"test-secret"
    token, _expires_at = issue_access_token(
        secret=secret,
        sub_id="main.us",
        audience="tvbox",
        access_code_hash=BCRYPT_HASH,
        now=100,
        ttl_seconds=60,
    )

    assert validate_access_token(token, secret=secret, sub_id="main.us", audience="tvbox", access_code_hash=BCRYPT_HASH, now=120)
    assert not validate_access_token(token, secret=secret, sub_id="main", audience="tvbox", access_code_hash=BCRYPT_HASH, now=120)


def test_failure_limiter_blocks_after_limit_and_clears() -> None:
    limiter = FailureLimiter(limit=2, cooldown_seconds=30)

    assert not limiter.record_failure("main|host", now=100)
    assert limiter.record_failure("main|host", now=101)
    assert limiter.is_limited("main|host", now=120)
    assert not limiter.is_limited("main|host", now=132)
    limiter.record_failure("main|host", now=133)
    limiter.clear("main|host")
    assert not limiter.is_limited("main|host", now=134)


def test_cooldown_limiter_allows_once_per_window() -> None:
    limiter = CooldownLimiter(short_window_seconds=5, long_window_seconds=300, long_limit=10)

    assert limiter.try_acquire("main|directory", now=100).allowed
    decision = limiter.try_acquire("main|directory", now=103)
    assert not decision.allowed
    assert decision.reason == "short_window"
    assert decision.remaining_seconds == 2
    assert limiter.try_acquire("main|directory", now=105).allowed


def test_cooldown_limiter_blocks_long_window_limit() -> None:
    limiter = CooldownLimiter(short_window_seconds=5, long_window_seconds=300, long_limit=3)

    assert limiter.try_acquire("main|directory", now=100).allowed
    assert limiter.try_acquire("main|directory", now=105).allowed
    assert limiter.try_acquire("main|directory", now=110).allowed
    decision = limiter.try_acquire("main|directory", now=115)

    assert not decision.allowed
    assert decision.reason == "long_window"
    assert decision.remaining_seconds == 285
    assert limiter.try_acquire("main|directory", now=400).allowed


def test_cooldown_limiter_prunes_expired_keys_on_acquire() -> None:
    limiter = CooldownLimiter(short_window_seconds=5, long_window_seconds=300, long_limit=10)

    assert limiter.try_acquire("main|one", now=100).allowed
    assert limiter.try_acquire("main|two", now=105).allowed
    assert limiter.try_acquire("main|three", now=410).allowed

    assert set(limiter._hits) == {"main|three"}


def test_config_auth_modes_are_validated(tmp_path) -> None:
    def load_with_sub(sub: dict) -> None:
        path = tmp_path / f"{time.time_ns()}.json"
        path.write_text(json.dumps({"subs": [sub]}), encoding="utf-8")
        load_config(str(path))

    load_with_sub({
        "id": "main",
        "type": "tvbox",
        "auth_mode": "anonymous",
        "tvbox": {"site_key": "dashbox", "sources": []},
    })
    load_with_sub({
        "id": "main",
        "type": "tvbox",
        "auth_mode": "access_code",
        "access_code_hash": BCRYPT_HASH,
        "tvbox": {"site_key": "dashbox", "sources": []},
    })

    with pytest.raises(ValueError, match="auth_mode is required"):
        load_with_sub({"id": "main", "type": "tvbox", "tvbox": {"site_key": "dashbox", "sources": []}})
    with pytest.raises(ValueError, match="unsupported auth_mode"):
        load_with_sub({
            "id": "main",
            "type": "tvbox",
            "auth_mode": "password",
            "tvbox": {"site_key": "dashbox", "sources": []},
        })
    with pytest.raises(ValueError, match="must not set access_code_hash"):
        load_with_sub({
            "id": "main",
            "type": "tvbox",
            "auth_mode": "anonymous",
            "access_code_hash": BCRYPT_HASH,
            "tvbox": {"site_key": "dashbox", "sources": []},
        })
    with pytest.raises(ValueError, match="requires access_code_hash"):
        load_with_sub({
            "id": "main",
            "type": "tvbox",
            "auth_mode": "access_code",
            "tvbox": {"site_key": "dashbox", "sources": []},
        })
    with pytest.raises(ValueError, match="plaintext"):
        load_with_sub({
            "id": "main",
            "type": "tvbox",
            "auth_mode": "anonymous",
            "access_code": "1234",
            "tvbox": {"site_key": "dashbox", "sources": []},
        })
