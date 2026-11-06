"""PostgreSQL limited-role smoke for prospect → consultation → agreement.

Uses distinct synthetic tenant principals, the actual FastAPI stack, all RLS
policies and migrations. Never passes live client data.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import Principal, get_principal
from app.db import engine
from app.main import app

identity = {"sub": ""}
def current_principal():
    return Principal(sub=identity["sub"])

app.dependency_overrides[get_principal] = current_principal
base = "/api/v1/orgs"

try:
    with engine.connect() as conn:
        role = conn.execute(text("SELECT current_user, rolsuper, rolbypassrls "
                                 "FROM pg_roles WHERE rolname = current_user")).one()
        assert role == ("immigrationos_app", False, False), "Must use restricted app role"
    with TestClient(app) as api:
        principals = []
        for idx in (1, 2):
            identity["sub"] = f"crm-smoke-{idx}-{uuid4()}"
            org = api.post(base, json={"name": f"Synthetic CRM {idx}",
                                      "slug": "crm-smoke-" + uuid4().hex})
            assert org.status_code == 201, (org.status_code, org.text)
            org_id = org.json()["id"]
            new = api.post(f"{base}/{org_id}/crm/prospects", json={
                "first_name": "Synthetic", "last_name": f"Prospect{idx}",
                "email": f"fake-{idx}-{uuid4().hex}@example.test",
                "source": "referral", "outreach_consent": False,
            })
            assert new.status_code == 201, (new.status_code, new.text)
            prospect_id = new.json()["id"]
            appointments = f"{base}/{org_id}/crm/prospects/{prospect_id}/consultations"
            start = datetime.now(timezone.utc) + timedelta(days=4)
            booked = api.post(appointments, json={
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(minutes=45)).isoformat(),
            })
            assert booked.status_code == 201, (booked.status_code, booked.text)
            appt_id = booked.json()["id"]
            prepared = api.post(appointments + f"/{appt_id}/agreements", json={
                "licensee_name": "Synthetic Consultant",
                "licensee_registration_number": "R000000",
                "licensee_address": "123 Example Lane, Ontario",
                "licensee_phone": "416-555-0000",
                "licensee_email": "consultant@example.test",
                "client_address": "1 Fictional Test Way, Ontario",
                "purpose_scope": "Discuss fictional case options with no legal advice provided.",
                "regulator_description": "The CICC is the statutory regulator overseeing licensees.",
                "fee_cents_cad": 0, "pro_bono": True,
            })
            assert prepared.status_code == 201, (prepared.status_code, prepared.text)
            assert prepared.json()["status"] == "draft_not_signed"
            assert api.post(appointments + f"/{appt_id}/complete").status_code == 409
            tasks = f"{base}/{org_id}/crm/prospects/{prospect_id}/follow-ups"
            due = datetime.now(timezone.utc) + timedelta(days=5)
            task = api.post(tasks, json={
                "title": "Recontact fictional lead", "due_at": due.isoformat(),
                "priority": "normal",
            })
            assert task.status_code == 201, (task.status_code, task.text)
            assert api.get(f"{base}/{org_id}/crm/follow-ups").json()["items"]
            completed = api.post(tasks + f"/{task.json()['id']}/complete")
            assert completed.status_code == 200, (completed.status_code, completed.text)
            assert completed.json()["status"] == "completed"
            principals.append((identity["sub"], org_id, prospect_id))

        for who, own_org, own_prospect in principals:
            identity["sub"] = who
            mine = api.get(f"{base}/{own_org}/crm/prospects")
            assert mine.status_code == 200 and len(mine.json()) == 1
            other_org, other_prospect = next((org, p) for user, org, p in principals if org != own_org)
            assert api.get(f"{base}/{other_org}/crm/prospects").status_code == 404
            assert api.get(f"{base}/{other_org}/crm/follow-ups").status_code == 404
            assert api.get(f"{base}/{other_org}/crm/prospects/{other_prospect}").status_code == 404
            assert api.get(f"{base}/{own_org}/crm/prospects/{other_prospect}").status_code == 404
finally:
    app.dependency_overrides.clear()

print("PASS: CRM PostgreSQL limited-role, cross-tenant isolation and unsigned consultation gate")
