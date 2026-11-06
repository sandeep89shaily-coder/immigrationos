"""Synthetic real-PostgreSQL smoke test of IRCC internal review audit + isolation.

Uses the limited application DB role and a temporary encrypted document store.
Source date is pinned for repeatable CI; deployment source checks remain live.
"""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.auth import Principal, get_principal
from app.main import app
from app.settings import get_settings
import app.form_preflight as preflight

identity = {"sub": "smoke-staff-" + uuid4().hex}
app.dependency_overrides[get_principal] = lambda: Principal(sub=identity["sub"])
real_source_metadata = preflight.source_metadata
preflight.source_metadata = lambda source, today=None: real_source_metadata(
    source, today=today or date(2026, 11, 6))

try:
    with TemporaryDirectory() as storage_root:
        get_settings().uploads_enabled = True
        get_settings().document_encryption_key = Fernet.generate_key().decode()
        get_settings().document_storage_root = storage_root
        with TestClient(app) as api:
            org = api.post("/api/v1/orgs", json={
                "name": "Fictional Preflight Firm", "slug": "preflight-" + uuid4().hex})
            assert org.status_code == 201, org.text
            org_id = org.json()["id"]
            client = api.post(f"/api/v1/orgs/{org_id}/clients", json={
                "first_name": "Avery", "last_name": "Synthetic"})
            assert client.status_code == 201, client.text
            case = api.post(f"/api/v1/orgs/{org_id}/cases", json={
                "client_id": client.json()["id"], "application_type": "study_permit",
                "title": "Fictional permit"})
            assert case.status_code == 201, case.text
            case_id = case.json()["id"]
            root = f"/api/v1/orgs/{org_id}/cases/{case_id}"
            document = api.post(root + "/documents",
                data={"document_type": "synthetic_employment_letter"},
                files={"file": ("fictional.txt", b"Synthetic case test only", "text/plain")})
            assert document.status_code == 201, document.text
            doc_id = document.json()["id"]
            for key, value in [
                ("identity.given_name", "Avery"),
                ("identity.family_name", "Synthetic"),
                ("identity.date_of_birth", "2001-01-02"),
                ("identity.citizenship", "Fictionland"),
                ("identity.passport_number", "TEST-1234"),
                ("education.institution", "Sample College"),
            ]:
                fact = api.post(root + "/facts", json={
                    "field_path": key, "value": value, "document_id": doc_id})
                assert fact.status_code == 201, fact.text
                verified = api.post(root + f"/facts/{fact.json()['id']}/review",
                                    json={"status": "verified"})
                assert verified.status_code == 200, verified.text

            path = (f"/api/v1/orgs/{org_id}/ircc/cases/{case_id}/forms/IMM1294/"
                    "preflight?filing_context=outside_canada")
            view = api.get(path)
            assert view.status_code == 200, view.text
            assert view.json()["internal_preflight_status"] == "reviewable", view.text
            ack_url = path.replace("?filing_context", "/acknowledge?filing_context")
            ack = api.post(ack_url, json={"snapshot_sha256": view.json()["snapshot_sha256"]})
            assert ack.status_code == 200 and ack.json()["acknowledgement"] == "current", ack.text
            assert api.get(path).json()["acknowledgement"] == "current"

            identity["sub"] = "unrelated-user-" + uuid4().hex
            assert api.get(path).status_code == 404
            assert api.post(ack_url, json={
                "snapshot_sha256": view.json()["snapshot_sha256"]}).status_code == 404
finally:
    app.dependency_overrides.clear()
    preflight.source_metadata = real_source_metadata

print("PASS: PostgreSQL IRCC preflight, evidence-bound acknowledgement, audit and firm denial")
