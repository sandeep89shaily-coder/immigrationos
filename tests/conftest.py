import os

# Must be defined before importing app modules (engine/settings are initialized on import).
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["AUTH_ISSUER"] = "https://issuer.example.invalid/realm"
os.environ["AUTH_AUDIENCE"] = "immigrationos-api"
os.environ["AUTH_JWKS_URL"] = "https://issuer.example.invalid/jwks"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.auth import Principal, get_principal
from app import portal_models, intake_models, crm_models, engagement_models, case_scope_models, staff_models, package_models, applicant_models, applicant_history_models  # register models for tests
from app.db import Base, engine, get_db
from app.main import app


@pytest.fixture
def api():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    subject = {"sub": "test-user-a", "email": None, "email_verified": False}

    def override_db():
        with factory() as db:
            yield db

    def override_principal():
        return Principal(sub=subject["sub"], email=subject["email"], email_verified=subject["email_verified"])

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_principal] = override_principal
    with TestClient(app) as client:
        yield client, subject, factory
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
