"""Limited-role PostgreSQL RCIC engagement checks with strictly synthetic PDF bytes.

Checks real RLS, composite client links, version screening, evidence review,
assignment and cross-firm rejection. Simulates (does NOT test) ClamAV for the
synthetic signed-copy fixture.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import text, create_engine
from sqlalchemy.exc import SQLAlchemyError

from app.auth import Principal, get_principal
from app.db import engine
from app.main import app  # import application before engagement to avoid cycle
from app.engagement import CLAUSES
from app import engagement

identity = {"sub": ""}
# Isolated CI schema-administration connection seeds fictional teammate roles;
# API requests below continue to run as the non-BYPASSRLS app database role.
assert 'MIGRATION_DATABASE_URL' in os.environ
schema_engine = create_engine(os.environ['MIGRATION_DATABASE_URL'])


def principal():
    return Principal(sub=identity["sub"])


app.dependency_overrides[get_principal] = principal

source = b"%PDF-1.4\nSynthetic signed service agreement\n%%EOF\n"
engagement.save_blob = lambda data, mime: (uuid4().hex, sha256(data).hexdigest())
engagement.load_blob = lambda key: source
engagement.delete_failed_blob = lambda key: None


class SyntheticScanner:
    status = "cleared"


engagement.scan_bytes = lambda data: SyntheticScanner()  # synthetic CI only; not ClamAV proof

try:
    with engine.connect() as conn:
        who = conn.execute(text("SELECT current_user, rolsuper, rolbypassrls "
                                "FROM pg_roles WHERE rolname = current_user")).one()
        assert who == ("immigrationos_app", False, False), "Must use limited, RLS-bound app role"

    with TestClient(app) as api:
        tenants = []
        for n in (1, 2):
            identity["sub"] = "engagement-pg-" + str(n) + "-" + str(uuid4())
            org = api.post("/api/v1/orgs", json={
                "name": "Fictional Engagement Firm " + str(n),
                "slug": "engagement-smoke-" + uuid4().hex,
            })
            assert org.status_code == 201, (org.status_code, org.text)
            org_id = org.json()["id"]
            owner_sub = identity["sub"]
            assistant_sub = "assistant-pg-" + uuid4().hex
            professional_sub = "consultant-pg-" + uuid4().hex
            with schema_engine.begin() as privileged:
                for sub, role in ((assistant_sub, "assistant"), (professional_sub, "consultant")):
                    privileged.execute(text("""INSERT INTO memberships
                        (id, org_id, subject, role, is_active, created_at)
                        VALUES (:id, :org, :sub, :role, true, :now)"""), {
                            "id": uuid4(), "org": org_id, "sub": sub,
                            "role": role, "now": datetime.now(timezone.utc),
                        })
            # The limited API DB role must NOT be able to self-join another
            # firm's membership table merely by changing PostgreSQL settings.
            with engine.begin() as limited:
                limited.execute(text("SELECT set_config('app.tenant_id', :tid, true)"),
                                {"tid": str(org_id)})
                limited.execute(text("SELECT set_config('app.principal_sub', :sub, true)"),
                                {"sub": "uninvited-pg-" + str(n)})
                try:
                    with limited.begin_nested():
                        limited.execute(text("""INSERT INTO memberships
                            (id, org_id, subject, role, is_active, created_at)
                            VALUES (:id, :org, :sub, 'owner', true, :now)"""), {
                                "id": uuid4(), "org": org_id,
                                "sub": "uninvited-pg-" + str(n), "now": datetime.now(timezone.utc),
                            })
                except SQLAlchemyError:
                    pass
                else:
                    raise AssertionError("RLS failed to block uninvited staff self-enrolment")
            client = api.post(f"/api/v1/orgs/{org_id}/clients", json={
                "first_name": "Synthetic", "last_name": "Client",
                "email": f"synthetic-{n}@example.test",
            })
            assert client.status_code == 201, (client.status_code, client.text)
            client_id = client.json()["id"]
            base = f"/api/v1/orgs/{org_id}/engagements/clients/{client_id}"

            assert api.post(base + "/open-matter", json={
                "application_type": "work_permit", "title": "Synthetic applicant",
                "professional_sub": identity["sub"],
                "confirm_engagement_and_professional_assignment": True,
            }).status_code == 409

            screened = api.post(base + "/screens", json={
                "client_identity_verified": True,
                "previous_rep_checked": True,
                "prior_rep": "none", "conflict_status": "none_identified",
                "details": "Synthetic identity, previous representation and conflict screen reviewed.",
                "independently_reviewed_conflicts": True,
            })
            assert screened.status_code == 201, (screened.status_code, screened.text)
            prepared = api.post(base + "/drafts", json={
                "clauses": {k: "Synthetic reviewed clause: " + label for k, label in CLAUSES.items()},
                "professional_checked_current_code": True,
            })
            assert prepared.status_code == 201, (prepared.status_code, prepared.text)
            draft_id = prepared.json()["id"]
            start = datetime.now(timezone.utc) + timedelta(seconds=1)
            uploaded = api.post(base + f"/drafts/{draft_id}/signed-copy", data={
                "draft_provided_at": start.isoformat(),
                "signed_at": (start + timedelta(seconds=1)).isoformat(),
                "client_copy_provided_at": (start + timedelta(seconds=2)).isoformat(),
            }, files={"file": ("signed-synthetic.pdf", source, "application/pdf")})
            assert uploaded.status_code == 201, (uploaded.status_code, uploaded.text)
            assert uploaded.json()["scan_status"] == "cleared"

            assert api.post(base + f"/drafts/{draft_id}/review", json={
                "decision": "accept",
                "reviewer_confirmed_signed_terms_and_delivery": True,
                "note": "Synthetic document, client copy and contract reviewed; CI-only scanner.",
            }).status_code == 200

            case = api.post(base + "/open-matter", json={
                "application_type": "work_permit", "title": "Synthetic work permit application",
                "professional_sub": professional_sub,
                "confirm_engagement_and_professional_assignment": True,
            })
            assert case.status_code == 201, (case.status_code, case.text)
            assert case.json()["regulated_authority_independently_verified"] is False
            case_id = case.json()["case_id"]
            root = f"/api/v1/orgs/{org_id}/cases/{case_id}"
            grant = api.post(root + "/staff/grants", json={
                "subject": assistant_sub, "scope": "read"})
            assert grant.status_code == 201, (grant.status_code, grant.text)
            identity["sub"] = assistant_sub
            assert api.get(root + "/facts").status_code == 200
            assert api.post(root + "/tasks", json={"title": "Denied due to read grant"}).status_code == 403
            identity["sub"] = professional_sub
            assert api.get(root + "/facts").status_code == 200
            assert len(api.get(f"/api/v1/orgs/{org_id}/cases").json()) == 1
            identity["sub"] = owner_sub
            revoked = api.post(root + "/staff/grants/" + grant.json()["id"] + "/revoke")
            assert revoked.status_code == 200, (revoked.status_code, revoked.text)
            identity["sub"] = assistant_sub
            assert api.get(root + "/facts").status_code == 404
            identity["sub"] = owner_sub
            assert len(api.get(f"/api/v1/orgs/{org_id}/cases").json()) == 1
            assert len(api.get(base + "/matters").json()) == 1
            linked = api.get(f"/api/v1/orgs/{org_id}/engagements/cases/{case.json()['case_id']}")
            assert linked.status_code == 200, (linked.status_code, linked.text)
            assert linked.json()["has_current_reviewed_signed_agreement"] is True
            revisions = api.get(base + "/history")
            assert revisions.status_code == 200
            assert revisions.json()["drafts"][0]["signed_copy"]["accepted_by_staff"] is True
            tenants.append((identity["sub"], org_id, client_id))

        for sub, own_org, own_client in tenants:
            identity["sub"] = sub
            own = api.get(f"/api/v1/orgs/{own_org}/engagements/clients/{own_client}")
            assert own.status_code == 200 and own.json()["eligible_for_engagement_gated_case_creation"]
            other_org, other_client = next(
                (org, c) for user, org, c in tenants if org != own_org)
            assert api.get(f"/api/v1/orgs/{other_org}/engagements/clients/{other_client}").status_code == 404
            assert api.get(f"/api/v1/orgs/{other_org}/engagements/clients/{other_client}/history").status_code == 404
            assert api.get(f"/api/v1/orgs/{own_org}/engagements/clients/{other_client}").status_code == 404

finally:
    app.dependency_overrides.clear()

print("PASS: Postgres RLS service engagement, signed proof, assigned matter and firm separation")
