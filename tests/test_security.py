from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError

from app import auth
from app.settings import Settings


def test_jwt_verifies_signature_issuer_audience_and_expiry(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(auth, "jwks_client", lambda: SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())))

    def payload(**changes):
        result = {
            "sub": "authorized-rcic", "iss": "https://issuer.example.invalid/realm",
            "aud": "immigrationos-api",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        }
        result.update(changes)
        return result

    def try_token(claims, signing_key=key):
        token = jwt.encode(claims, signing_key, algorithm="RS256")
        return auth.get_principal(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))

    assert try_token(payload()).sub == "authorized-rcic"
    for claims, signing_key in [
        (payload(aud="wrong-audience"), key),
        (payload(iss="https://other.invalid"), key),
        (payload(exp=datetime.now(timezone.utc) - timedelta(minutes=5)), key),
        (payload(), other_key),
    ]:
        with pytest.raises(HTTPException) as exc:
            try_token(claims, signing_key)
        assert exc.value.status_code == 401


def test_missing_token_is_rejected():
    with pytest.raises(HTTPException) as exc:
        auth.get_principal(None)
    assert exc.value.status_code == 401


def test_production_rejects_insecure_configuration():
    with pytest.raises(ValidationError):
        Settings(environment="production", database_url="sqlite:///:memory:",
                 auth_issuer="http://localhost:8080", auth_jwks_url="http://localhost/jwks",
                 auth_audience="immigrationos-api")
    with pytest.raises(ValidationError):
        Settings(environment="test", database_url="sqlite:///:memory:",
                 auth_issuer="https://issuer.example", auth_jwks_url="https://issuer.example/jwks",
                 auth_audience="immigrationos-api", cors_origins="*")
