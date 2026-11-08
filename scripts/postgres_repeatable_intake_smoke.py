"""Real PostgreSQL restricted-role repeatable proposal and consultant-import smoke."""
from uuid import uuid4
from fastapi.testclient import TestClient

from app.auth import Principal, get_principal
from app.main import app

who = {"sub": "repeatable-staff-" + uuid4().hex,
       "email": None, "verified": False}


def principal():
    return Principal(sub=who["sub"], email=who["email"],
                     email_verified=who["verified"])


app.dependency_overrides[get_principal] = principal
try:
    with TestClient(app) as api:
        staff = who["sub"]
        org_result = api.post("/api/v1/orgs", json={
            "name": "Fictional repeatable study firm",
            "slug": "repeatable-ci-" + uuid4().hex})
        assert org_result.status_code == 201, org_result.text
        org = org_result.json()["id"]
        person = api.post(f"/api/v1/orgs/{org}/clients", json={
            "first_name": "Fictional", "last_name": "Client",
            "email": "repeatable-" + uuid4().hex + "@example.test"})
        assert person.status_code == 201, person.text
        email = person.json()["email"]
        case = api.post(f"/api/v1/orgs/{org}/cases", json={
            "client_id": person.json()["id"], "application_type": "study_permit",
            "title": "Fictional repeatable testing"})
        assert case.status_code == 201, case.text
        case_id = case.json()["id"]
        inv = api.post(f"/api/v1/orgs/{org}/cases/{case_id}/portal/invitations")
        assert inv.status_code == 201, inv.text
        who.update(sub="repeatable-recipient-" + uuid4().hex, email=email, verified=True)
        portal_sub = who["sub"]
        claimed = api.post("/api/v1/client/invitations/accept",
                           json={"token": inv.json()["invite_token"]})
        assert claimed.status_code == 200, claimed.text

        url = f"/api/v1/client/cases/{case_id}/repeatables"
        schema = api.get(url)
        assert schema.status_code == 200, schema.text
        proposal = api.post(url, json={
            "template_version": schema.json()["template_version"],
            "acknowledged_notice": True, "kind": "family",
            "details": {"relationship": "child", "given_name": "Imaginary",
                        "family_name": "Dependent", "date_of_birth": "2012-05-01"}})
        assert proposal.status_code == 201, proposal.text
        proposal_id = proposal.json()["id"]
        assert api.get(url).json()["proposals"][0]["details"] is None

        who.update(sub=staff, email=None, verified=False)
        staff_url = f"/api/v1/orgs/{org}/cases/{case_id}/repeatables"
        listing = api.get(staff_url)
        assert listing.status_code == 200, listing.text
        assert listing.json()["pending_count"] == 1
        accepted = api.post(staff_url + f"/{proposal_id}/decide",
                            json={"decision": "accept"})
        assert accepted.status_code == 201, accepted.text
        assert accepted.json()["verified_evidence"] is False
        family = api.get(f"/api/v1/orgs/{org}/clients/{person.json()['id']}/applicant")
        assert family.status_code == 200, family.text
        assert len(family.json()["family"]) == 1
        assert family.json()["verified_for_official_forms"] is False
        assert api.post(staff_url + f"/{proposal_id}/decide",
                        json={"decision": "accept"}).status_code == 409

        who.update(sub=portal_sub,email=email,verified=True)
        relationships=api.post(url,json={
            "template_version":schema.json()["template_version"],
            "acknowledged_notice":True,"kind":"previous_relationship",
            "details":{"relationship_type":"married","family_name":"Former",
                       "given_name":"Sample","date_of_birth":"1985-06-01",
                       "start_date":"2006-01-01","end_date":"2012-01-01"}})
        assert relationships.status_code==201,relationships.text
        residence=api.post(url,json={
            "template_version":schema.json()["template_version"],
            "acknowledged_notice":True,"kind":"foreign_residence",
            "details":{"country":"Fictionland","status":"other",
                       "status_other":"Synthetic temporary status",
                       "start_date":"2019-01-01","end_date":"2020-05-01"}})
        assert residence.status_code==201,residence.text
        assert api.get(staff_url+"/master-records").status_code==404
        who.update(sub=staff,email=None,verified=False)
        for proposal in (relationships,residence):
            checked=api.post(staff_url+f"/{proposal.json()['id']}/decide",
                             json={"decision":"accept"})
            assert checked.status_code==201,checked.text
            assert checked.json()["verified_evidence"] is False
        supplemental=api.get(staff_url+"/master-records")
        assert supplemental.status_code==200,supplemental.text
        assert {r["kind"] for r in supplemental.json()["records"]}=={
            "previous_relationship","foreign_residence"}
        assert supplemental.json()["verified_evidence"] is False

        who.update(sub="repeatable-unrelated-" + uuid4().hex,
                   email=None, verified=False)
        assert api.get(staff_url).status_code == 404
        assert api.post(staff_url + f"/{proposal_id}/decide",
                        json={"decision": "dismiss"}).status_code == 404
        assert api.get(url).status_code == 403 or api.get(url).status_code == 404
finally:
    app.dependency_overrides.clear()

print("PASS: PostgreSQL portal repeatable intake, staff-only import and revocation gate")
