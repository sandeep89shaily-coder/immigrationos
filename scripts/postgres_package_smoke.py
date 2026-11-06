"""Real PostgreSQL restricted-role smoke for the first IRCC application package.

The synthetic PDF bytes and scanner are test doubles. No real government
form or ClamAV instance is claimed as validated.
"""
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.auth import Principal, get_principal
from app.db import engine
from app.main import app
from app import application_package as package_api
import os

assert "MIGRATION_DATABASE_URL" in os.environ
migration_engine = create_engine(os.environ["MIGRATION_DATABASE_URL"])
document = b"%PDF-1.4\nFictional test only\n%%EOF\n"
package_api.load_blob = lambda key: document


class DummyScan:
    status = "cleared"


package_api.scan_bytes = lambda bytes_: DummyScan()  # fake scanner ONLY for test fixtures
active = {"sub": ""}


def principal():
    return Principal(sub=active["sub"])


app.dependency_overrides[get_principal] = principal

try:
    with engine.connect() as db:
        identity = db.execute(text("""SELECT current_user, rolsuper, rolbypassrls
            FROM pg_roles WHERE rolname=current_user""")).one()
        assert identity == ("immigrationos_app", False, False)

    with TestClient(app) as api:
        tenants = []
        for n in (1, 2):
            active["sub"] = f"package-pg-{n}-{uuid4().hex}"
            org_r = api.post("/api/v1/orgs", json={
                "name": f"Synthetic Worklist Firm {n}",
                "slug": f"package-smoke-{uuid4().hex}"})
            assert org_r.status_code == 201, (org_r.status_code, org_r.text)
            org = org_r.json()["id"]
            person = api.post(f"/api/v1/orgs/{org}/clients", json={
                "first_name": "Synthetic", "last_name": f"Client{n}"})
            assert person.status_code == 201, (person.status_code, person.text)
            case_r = api.post(f"/api/v1/orgs/{org}/cases", json={
                "client_id": person.json()["id"],
                "application_type": "study_permit",
                "title": "Synthetic application package"})
            assert case_r.status_code == 201, (case_r.status_code, case_r.text)
            case = case_r.json()["id"]
            root = f"/api/v1/orgs/{org}/cases/{case}/package"

            result = api.post(root, json={
                "filing_context": "inside_canada" if n == 1 else "outside_canada",
                "include_representative_form": True,
            })
            assert result.status_code == 201, (result.status_code, result.text)
            codes = [s["code"] for s in result.json()["forms"]]
            assert codes == (["IMM5709", "IMM5476"] if n == 1 else
                             ["IMM1294", "IMM5476"])
            assert result.json()["submission_supported"] is False
            assert result.json()["document_requirements"]
            doc_id = uuid4()
            with migration_engine.begin() as admin:
                admin.execute(text("""INSERT INTO case_documents
                    (id,org_id,case_id,filename,document_type,mime_type,
                     size_bytes,sha256,storage_key,uploaded_by_sub,created_at)
                    VALUES (:id,:org,:case,'synthetic-form.pdf','ircc_form',
                    'application/pdf',:size,:sha,:storage,:owner,:now)
                """), {
                    "id": doc_id, "org": org, "case": case,
                    "size": len(document),
                    "sha": sha256(document).hexdigest(),
                    "storage": uuid4().hex, "owner": active["sub"],
                    "now": datetime.now(timezone.utc),
                })

            copy = api.post(root + f"/forms/{codes[0]}/copies", json={
                "document_id": str(doc_id)})
            assert copy.status_code == 201, (copy.status_code, copy.text)
            assert copy.json()["scan_status"] == "cleared"
            review = api.post(root + f"/copies/{copy.json()['copy_id']}/review", json={
                "decision": "accept",
                "note": "Fictional case form copy reviewed under limited PostgreSQL role.",
                "current_ircc_source_checked": True,
                "reviewed_pdf_in_appropriate_software": True,
            })
            assert review.status_code == 200, (review.status_code, review.text)
            assert review.json()["submission_supported"] is False
            assert api.get(root).json()["forms"][0]["status"] == "staff_reviewed_copy"
            tenants.append((active["sub"], org, case, str(doc_id), codes[0]))

        for who, own_org, own_case, _, own_form in tenants:
            active["sub"] = who
            foreign = next(x for x in tenants if x[1] != own_org)
            foreign_org, foreign_case, foreign_doc = foreign[1:4]
            assert api.get(f"/api/v1/orgs/{foreign_org}/cases/{foreign_case}/package").status_code == 404
            assert api.post(f"/api/v1/orgs/{own_org}/cases/{own_case}/package/forms/{own_form}/copies",
                            json={"document_id": foreign_doc}).status_code == 404

finally:
    app.dependency_overrides.clear()

print("PASS: package links same-case evidence, RCIC review and restricted PostgreSQL tenant RLS")
