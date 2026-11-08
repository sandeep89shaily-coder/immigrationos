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


def test_family_snapshot_is_frozen_and_draft_freshness_changes(api):
    client, who, factory = api
    org, case, root = case_setup(api, "family-draft-freshness")
    assert start(client, root, representative=False).status_code == 201
    cid = next(row["client_id"] for row in client.get(
        f"/api/v1/orgs/{org}/cases").json() if row["id"] == case)
    applicant = f"/api/v1/orgs/{org}/clients/{cid}/applicant"
    relative_url = f"/api/v1/orgs/{org}/clients/{cid}/family"
    drafts = f"/api/v1/orgs/{org}/cases/{case}/answer-drafts"
    assert client.put(applicant, json={"identity": {
        "given_name": "Fictional", "family_name": "Client"}}).status_code == 200
    relative = {"relationship": "child", "given_name": "Synthetic",
                "family_name": "Child", "date_of_birth": "2010-01-02"}
    first_member = client.post(relative_url, json=relative)
    assert first_member.status_code == 201
    member_id = first_member.json()["id"]
    original = client.post(drafts)
    assert original.status_code == 201, original.text
    first = original.json()
    assert first["source_freshness"] == "current"
    assert first["family_snapshot"][0]["given_name"] == "Synthetic"
    assert len(first["manifest_sha256"]) == 64
    assert client.get(drafts).json()[0]["source_freshness"] == "current"

    changed = client.put(relative_url + "/" + member_id, json={
        **relative, "expected_version": 1, "given_name": "Updated"})
    assert changed.status_code == 200, changed.text
    historical = client.get(drafts).json()[0]
    assert historical["source_freshness"] == "stale"
    assert historical["family_snapshot"][0]["given_name"] == "Synthetic"
    latest = client.post(drafts)
    assert latest.status_code == 201, latest.text
    assert latest.json()["family_snapshot"][0]["given_name"] == "Updated"
    listed = client.get(drafts).json()
    assert listed[0]["source_freshness"] == "current"
    assert listed[1]["source_freshness"] == "stale"

    added = client.post(relative_url, json={
        "relationship": "parent", "given_name": "Another", "family_name": "Relative"})
    assert added.status_code == 201
    assert all(row["source_freshness"] == "stale" for row in client.get(drafts).json())


def test_new_case_drafts_block_closed_matters_and_legacy_unknown(api):
    from app.applicant_models import CaseAnswerDraft
    from app.models import Case
    from uuid import UUID
    client, _, factory = api
    org, case, root = case_setup(api, "family-draft-legacy")
    assert start(client, root, representative=False).status_code == 201
    cid = next(row["client_id"] for row in client.get(
        f"/api/v1/orgs/{org}/cases").json() if row["id"] == case)
    applicant = f"/api/v1/orgs/{org}/clients/{cid}/applicant"
    drafts = f"/api/v1/orgs/{org}/cases/{case}/answer-drafts"
    assert client.put(applicant, json={"identity": {"given_name": "Sample"}}).status_code == 200
    original = client.post(drafts).json()
    with factory() as db:
        row = db.query(CaseAnswerDraft).filter(CaseAnswerDraft.id == UUID(original["id"])).one()
        row.history_snapshot = {"records": []}  # historical record predating family tracking
        db.commit()
    assert client.get(drafts).json()[0]["source_freshness"] == "unknown_legacy"
    with factory() as db:
        row = db.query(Case).filter(Case.id == UUID(case)).one()
        row.status = "closed"
        db.commit()
    assert client.post(drafts).status_code == 409
    assert client.get(drafts).status_code == 200
