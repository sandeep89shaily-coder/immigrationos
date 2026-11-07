"""Actual restricted-role PostgreSQL smoke for IMM5476 review checkpoints.

Uses fictional data and an explicitly mocked scan verdict. No client PDF,
licensed vendor call or IRCC form submission is involved.
"""
import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.auth import Principal, get_principal
from app.db import engine
from app.main import app
from app import imm5476_packets as review

assert "MIGRATION_DATABASE_URL" in os.environ
migration_engine = create_engine(os.environ["MIGRATION_DATABASE_URL"])
identity = {"sub": ""}


def principal():
    return Principal(sub=identity["sub"])


app.dependency_overrides[get_principal] = principal
# Mock ONLY the scanner's preexisting external disposition on a known synthetic
# document. All case facts and documents are read from the actual app-role DB.
synthetic_documents = {}
review.scan_status_by_document = lambda db, org, case: (
    {synthetic_documents[(str(org), str(case))]: "cleared"}
    if (str(org), str(case)) in synthetic_documents else {})

try:
    with engine.connect() as connection:
        role = connection.execute(text("""SELECT current_user, rolsuper, rolbypassrls
            FROM pg_roles WHERE rolname=current_user""")).one()
        assert role == ("immigrationos_app", False, False), role

    with TestClient(app) as api:
        tenants = []
        for n in (1, 2):
            identity["sub"] = f"imm5476-smoke-{n}-{uuid4().hex}"
            created = api.post("/api/v1/orgs", json={
                "name": f"Fictional RCIC Firm {n}",
                "slug": f"imm5476-packets-{uuid4().hex}"})
            assert created.status_code == 201, created.text
            org = created.json()["id"]
            person = api.post(f"/api/v1/orgs/{org}/clients", json={
                "first_name": "Fictional", "last_name": "Applicant"})
            assert person.status_code == 201, person.text
            case_created = api.post(f"/api/v1/orgs/{org}/cases", json={
                "client_id": person.json()["id"],
                "application_type": "study_permit",
                "title": "Fictional representation appointment"})
            assert case_created.status_code == 201, case_created.text
            case = case_created.json()["id"]
            root = f"/api/v1/orgs/{org}/cases/{case}"
            started = api.post(root + "/package", json={
                "filing_context": "outside_canada",
                "include_representative_form": True})
            assert started.status_code == 201, started.text

            document_id = uuid4()
            now = datetime.now(timezone.utc)
            with migration_engine.begin() as admin:
                admin.execute(text("""INSERT INTO case_documents
                    (id,org_id,case_id,filename,document_type,mime_type,
                     size_bytes,sha256,storage_key,uploaded_by_sub,created_at)
                    VALUES (:id,:org,:case,'fictional-review.pdf','identity',
                    'application/pdf',100,:sha,:storage,:owner,:now)"""),
                    {"id": document_id, "org": org, "case": case,
                     "sha": "b"*64, "storage": uuid4().hex,
                     "owner": identity["sub"], "now": now})
                admin.execute(text("""INSERT INTO case_facts
                    (id,org_id,case_id,document_id,field_path,value,
                     review_status,created_by_sub,reviewed_by_sub,created_at)
                    VALUES (:id,:org,:case,:doc,'identity.given_name',
                    'Fictional Reviewed Value','verified',:owner,:owner,:now)"""),
                    {"id": uuid4(), "org": org, "case": case,
                     "doc": document_id, "owner": identity["sub"], "now": now})
            synthetic_documents[(org, case)] = document_id

            prep = api.get(root + "/ircc/IMM5476/preparation")
            assert prep.status_code == 200, prep.text
            # The preview uses the actual unmocked scan map, so its value is
            # not accepted yet; use the independently recomputed protected
            # checkpoint hash in this scanner-mocked synthetic smoke.
            # The preview's scan function is patched only for this synthetic
            # test, exactly as a cleared scan disposition would be recorded.
            from app import imm5476_case_preview as preview_module
            original_scan = preview_module.scan_status_by_document
            preview_module.scan_status_by_document = review.scan_status_by_document
            try:
                new_preview = api.get(root + "/ircc/IMM5476/preparation")
                assert new_preview.status_code == 200, new_preview.text
                assert new_preview.json()["verified_text_fields"] == 1
                response = api.post(root + "/ircc/IMM5476/packets", json={
                    "expected_sha256": new_preview.json()["snapshot_sha256"],
                    "acknowledge_internal_only": True})
                assert response.status_code == 201, response.text
                packet = response.json()
                assert packet["is_current"] and not packet["verified_observed_subset"]
                assert packet["fields"][0]["value"] == "Fictional Reviewed Value"
                assert packet["submission_supported"] is False
                assert api.get(root + "/ircc/IMM5476/packets").json()[0]["id"] == packet["id"]
                assert api.post(root + "/ircc/IMM5476/packets", json={
                    "expected_sha256": new_preview.json()["snapshot_sha256"],
                    "acknowledge_internal_only": True}).status_code == 409
            finally:
                preview_module.scan_status_by_document = original_scan
            tenants.append((identity["sub"], org, case))

        for principal_id, own_org, own_case in tenants:
            identity["sub"] = principal_id
            foreign = next(t for t in tenants if t[1] != own_org)
            foreign_root = (f"/api/v1/orgs/{foreign[1]}/cases/{foreign[2]}"
                            "/ircc/IMM5476/packets")
            assert api.get(foreign_root).status_code == 404
            assert api.post(foreign_root, json={
                "expected_sha256": "0"*64,
                "acknowledge_internal_only": True}).status_code == 404
finally:
    app.dependency_overrides.clear()

print("PASS: restricted PostgreSQL IMM5476 checkpoint create/re-read, duplicate rejection and firm isolation")
