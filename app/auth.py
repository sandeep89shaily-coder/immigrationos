from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.settings import get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    sub: str


@lru_cache(maxsize=1)
def jwks_client() -> PyJWKClient:
    return PyJWKClient(get_settings().auth_jwks_url, cache_jwk_set=True, lifespan=300)


def get_principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer token required", headers={"WWW-Authenticate": "Bearer"})
    try:
        signing_key = jwks_client().get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256"],
            audience=get_settings().auth_audience,
            issuer=get_settings().auth_issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
            leeway=30,
        )
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject or len(subject) > 255:
            raise ValueError("Invalid subject")
        return Principal(sub=subject)
    except Exception:
        # Never log token contents, claims, or source documents.
        raise HTTPException(status_code=401, detail="Invalid or expired bearer token", headers={"WWW-Authenticate": "Bearer"}) from None
