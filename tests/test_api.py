"""Tests for API endpoints (unit-level, no DB)."""
import pytest
from src.api.auth import hash_password, verify_password, create_token, decode_token


def test_password_hash_verify():
    hashed = hash_password("test123")
    assert verify_password("test123", hashed)
    assert not verify_password("wrong", hashed)


def test_create_and_decode_token():
    token = create_token("admin", "admin")
    payload = decode_token(token)
    assert payload["sub"] == "admin"
    assert payload["role"] == "admin"


def test_decode_invalid_token():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        decode_token("invalid.token.here")
    assert exc_info.value.status_code == 401
