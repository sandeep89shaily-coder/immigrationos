"""End-to-end synthetic applicant/family and answer-draft regression coverage."""
from uuid import UUID
from app.models import Membership
from tests.test_application_package import case_setup, start
from tests.test_api import new_org, new_client


def test_master_profile_version_and_case_answer_snapshot(api):
    client, who, factory = api
    org, case, root = case_setup(api, "applicant-snapshot")
    # Case worklist and applicant profile are independent reusable building blocks.
    assert start(client, root, representative=False).status_code == 201
    case_record = client.get(f"/api/v1/orgs/{org}/cases").json()[0]
    client_id = case_record["client_id"]
    base = f"/api/v1/orgs/{org}/clients/{client_id}/applicant"
    assert client.get(base).json()["profile"] is None
    before = client.post(f"/api/v1/orgs/{org}/cases/{case}/answer-drafts")
    assert before.status_code == 409
    identity = {"identity": {
        "given_name": "Sample", "family_name": "Applicant",
        "date_of_birth": "2000-01-02", "citizenship": "Fictionland",
        "passport_number": "FICTIONAL-0001",
    }}
    created = client.put(base, json=identity)
    assert created.status_code == 200, created.text
    assert created.json()["version"] == 1
    assert client.put(base, json=identity).status_code == 409
    draft = client.post(f"/api/v1/orgs/{org}/cases/{case}/answer-drafts")
    assert draft.status_code == 201, draft.text
    first = draft.json()
    assert first["form_code"] == "IMM1294"
    assert first["answers"]["identity.given_name"] == "Sample"
    assert first["profile_version"] == 1
    assert first["official_pdf_autofill_supported"] is False
    assert first["submission_supported"] is False
    identity["expected_version"] = 1
    identity["identity"]["given_name"] = "Updated"
    assert client.put(base, json=identity).json()["version"] == 2
    new_draft = client.post(f"/api/v1/orgs/{org}/cases/{case}/answer-drafts").json()
    assert new_draft["answers"]["identity.given_name"] == "Updated"
    snapshots = client.get(f"/api/v1/orgs/{org}/cases/{case}/answer-drafts").json()
    assert len(snapshots) == 2
    assert snapshots[0]["profile_version"] == 2
    assert snapshots[1]["answers"]["identity.given_name"] == "Sample"


def test_family_relations_validation_and_cross_firm_isolation(api):
    client, who, factory = api
    org = new_org(client, "family-main")
    client_id = new_client(client, org)
    base = f"/api/v1/orgs/{org}/clients/{client_id}"
    relative = {"relationship": "child", "given_name": "Fictional",
                "family_name": "Child", "date_of_birth": "2014-05-01"}
    added = client.post(base + "/family", json=relative)
    assert added.status_code == 201, added.text
    mid = added.json()["id"]
    assert client.get(base + "/applicant").json()["family"][0]["id"] == mid
    assert client.post(base + "/family", json={**relative, "relationship": "unknown"}).status_code == 422
    assert client.put(base + f"/family/{mid}", json={**relative, "expected_version": 2}).status_code == 409
    changed = client.put(base + f"/family/{mid}", json={**relative,
                         "expected_version": 1, "given_name": "Revised"})
    assert changed.status_code == 200
    assert changed.json()["version"] == 2
    who["sub"] = "another-org-owner"
    other_org = new_org(client, "family-foreign")
    other_client = new_client(client, other_org)
    assert client.get(base + "/applicant").status_code == 404
    assert client.put(base + "/applicant", json={"identity": {}}).status_code == 404
    assert client.put(base + f"/family/{mid}", json={**relative, "expected_version": 2}).status_code == 404
    assert client.get(f"/api/v1/orgs/{other_org}/clients/{other_client}/applicant").status_code == 200


def test_firm_member_without_client_access_cannot_read_master_profile(api):
    client, who, factory = api
    org = new_org(client, "family-member")
    client_id = new_client(client, org)
    base = f"/api/v1/orgs/{org}/clients/{client_id}/applicant"
    assert client.put(base, json={"identity": {"given_name": "Sensitive"}}).status_code == 200
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="unassigned-consultant",
                          role="consultant", is_active=True))
        db.commit()
    who["sub"] = "unassigned-consultant"
    assert client.get(base).status_code == 404
    assert client.put(base, json={"identity": {"given_name": "Other"}}).status_code == 404
