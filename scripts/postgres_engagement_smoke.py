"""Limited-role PostgreSQL RCIC engagement checks with strictly synthetic PDF bytes.

Checks real RLS, composite client links, version screening, evidence review,
assignment and cross-firm rejection. Simulates (does NOT test) ClamAV for the
synthetic signed-copy fixture.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import Principal, get_principal
from app.db import engine
from app.engagement import CLAUSES
from app import engagement
from app.main import app

identity = {"sub": ""}


def principal():
    return Principal(sub=identity["sub"])


app.dependency_overrides[get_principal] = principal

source = b"%PDF-1.4\nSynthetic signed service agreement\n%%EOF\n"
engagement.save_blob = lambda data, mime: ("2"*32, sha256(data).hexdigest())
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
                "professional_sub": identity["sub"],
                "confirm_engagement_and_professional_assignment": True,
            })
            assert case.status_code == 201, (case.status_code, case.text)
            assert case.json()["regulated_authority_independently_verified"] is False
            assert len(api.get(base + "/matters").json()) == 1
            tenants.append((identity["sub"], org_id, client_id))

        for sub, own_org, own_client in tenants:
            identity["sub"] = sub
            own = api.get(f"/api/v1/orgs/{own_org}/engagements/clients/{own_client}")
            assert own.status_code == 200 and own.json()["eligible_for_engagement_gated_case_creation"]
            other_org, other_client = next(
                (org, c) for user, org, c in tenants if org != own_org)
            assert api.get(f"/api/v1/orgs/{other_org}/engagements/clients/{other_client}").status_code == 404
            assert api.get(f"/api/v1/orgs/{own_org}/engagements/clients/{other_client}").status_code == 404

finally:
    app.dependency_overrides.clear()

print("PASS: Postgres RLS service engagement, signed proof, assigned matter and firm separation")
