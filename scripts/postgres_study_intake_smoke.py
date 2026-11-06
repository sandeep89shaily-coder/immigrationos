"""PostgreSQL restricted-role smoke: versioned questionnaire + human review.

Requires a migrated synthetic CI database under immigrationos_app (RLS enabled).
"""
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth import Principal, get_principal
from app.main import app

who = {"sub": "intake-staff-" + uuid4().hex, "email": None, "verified": False}


def principal():
    return Principal(sub=who["sub"], email=who["email"], email_verified=who["verified"])


app.dependency_overrides[get_principal] = principal
try:
    with TestClient(app) as api:
        staff_sub = who["sub"]
        org = api.post("/api/v1/orgs", json={
            "name": "Fictional study intake firm", "slug": "intake-ci-" + uuid4().hex})
        assert org.status_code == 201, org.text
        org_id = org.json()["id"]
        client = api.post(f"/api/v1/orgs/{org_id}/clients", json={
            "first_name": "Avery", "last_name": "Synthetic",
            "email": "fake-" + uuid4().hex + "@example.test"})
        assert client.status_code == 201, client.text
        email = client.json()["email"]
        case = api.post(f"/api/v1/orgs/{org_id}/cases", json={
            "client_id": client.json()["id"], "application_type": "study_permit",
            "title": "Fictional study-permit intake"})
        assert case.status_code == 201, case.text
        case_id = case.json()["id"]
        invite = api.post(f"/api/v1/orgs/{org_id}/cases/{case_id}/portal/invitations")
        assert invite.status_code == 201, invite.text

        who.update(sub="intake-recipient-" + uuid4().hex, email=email, verified=True)
        claimed = api.post("/api/v1/client/invitations/accept",
                           json={"token": invite.json()["invite_token"]})
        assert claimed.status_code == 200, claimed.text
        url = f"/api/v1/client/cases/{case_id}/study-intake"
        template = api.get(url)
        assert template.status_code == 200, template.text
        answers = {
            "identity.given_name": "Avery",
            "identity.family_name": "Synthetic",
            "identity.date_of_birth": "2000-01-02",
            "identity.citizenship": "Fictionland",
            "identity.passport_number": "FAKE-TEST-ONLY",
            "education.institution": "Example College",
        }
        saved = api.post(url + "/submissions", json={
            "template_version": template.json()["template_version"],
            "acknowledged_notice": True,
            "answers": answers,
        })
        assert saved.status_code == 201, saved.text
        submission_id = saved.json()["id"]
        assert api.get(url).json()["last_submission_id"] == submission_id

        who.update(sub=staff_sub, email=None, verified=False)
        staff_url = f"/api/v1/orgs/{org_id}/cases/{case_id}/study-intake"
        listed = api.get(staff_url)
        assert listed.status_code == 200, listed.text
        assert listed.json()["current_submission_id"] == submission_id
        decision = api.post(
            staff_url + f"/{submission_id}/answers/identity.given_name/decide",
            json={"decision": "accept"})
        assert decision.status_code == 201, decision.text
        assert decision.json()["fact_status"] == "pending"
        facts = api.get(f"/api/v1/orgs/{org_id}/cases/{case_id}/facts")
        assert facts.status_code == 200
        assert any(f["id"] == decision.json()["created_fact_id"] and
                   f["review_status"] == "pending" and f["document_id"] is None
                   for f in facts.json())

        who.update(sub="unrelated-" + uuid4().hex, email=None, verified=False)
        assert api.get(staff_url).status_code == 404
        assert api.post(staff_url + f"/{submission_id}/answers/identity.family_name/decide",
                        json={"decision": "accept"}).status_code == 404

finally:
    app.dependency_overrides.clear()

print("PASS: PostgreSQL client intake submission, staff review and tenant denial")
