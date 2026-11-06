"""Synthetic history CRUD, chronology, isolation, evidence-gate and snapshot tests."""
from uuid import UUID
from app.models import CaseFact, Membership
from tests.test_application_package import case_setup, start
from tests.test_api import new_org, new_client


def context(api, slug):
    client, who, factory = api
    org, case, root = case_setup(api, slug)
    assert start(client, root, representative=False).status_code == 201
    case_record = next(row for row in client.get(f"/api/v1/orgs/{org}/cases").json()
                       if row["id"] == case)
    cid = case_record["client_id"]
    return org, case, cid, f"/api/v1/orgs/{org}/clients/{cid}/histories"


def test_histories_strict_validation_and_versioning(api):
    client, who, factory = api
    org, case, cid, root = context(api, "history-crud")
    address = {"start_date": "2024-01-01", "line1": "1 Sample Ave",
               "city": "Example City", "country": "Fictionland"}
    assert client.post(root + "/address", json={"details": {**address,
                         "end_date": "2023-12-31"}}).status_code == 422
    assert client.post(root + "/address", json={"details": {**address,
                         "unsupported": "x"}}).status_code == 422
    assert client.post(root + "/bad_kind", json={"details": address}).status_code == 404
    created = client.post(root + "/address", json={"details": address})
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["version"] == 1
    assert record["verified_evidence"] is False
    assert client.get(root).json()["records"][0]["details"]["city"] == "Example City"
    assert client.put(root + "/address/" + record["id"], json={
        "details": {**address, "city": "Revised"}, "expected_version": 3}).status_code == 409
    changed = client.put(root + "/address/" + record["id"], json={
        "details": {**address, "city": "Revised"}, "expected_version": 1})
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == 2
    assert changed.json()["details"]["city"] == "Revised"
    assert client.put(root + "/travel/" + record["id"], json={
        "details": {"start_date": "2024-01-01", "purpose": "Holiday",
                    "destination_country": "Fictionland"}, "expected_version": 2}).status_code == 404


def test_all_history_kinds_freeze_in_case_draft(api):
    client, who, factory = api
    org, case, cid, root = context(api, "history-snapshot")
    samples = {
        "address": {"start_date": "2022-01-01", "line1": "4 Demo St",
                    "city": "Fiction Town", "country": "Exampleland"},
        "education": {"start_date": "2019-09-01", "end_date": "2022-05-01",
                      "institution": "Imaginary University", "country": "Exampleland",
                      "program": "Demo degree"},
        "employment": {"start_date": "2023-01-01", "employer": "Fiction Employer",
                       "position": "Tester", "country": "Exampleland",
                       "employment_status": "employed"},
        "travel": {"start_date": "2024-08-01", "end_date": "2024-08-10",
                   "destination_country": "Fictionland", "purpose": "Holiday"},
    }
    entries = {}
    for kind, details in samples.items():
        r = client.post(root + "/" + kind, json={"details": details})
        assert r.status_code == 201, r.text
        entries[kind] = r.json()
    master = f"/api/v1/orgs/{org}/clients/{cid}/applicant"
    assert client.put(master, json={"identity": {"given_name": "Synthetic",
                  "family_name": "Person"}}).status_code == 200
    drafts = f"/api/v1/orgs/{org}/cases/{case}/answer-drafts"
    first = client.post(drafts)
    assert first.status_code == 201, first.text
    previous = first.json()["history_snapshot"]["records"]
    assert len(previous) == 4
    assert {item["kind"] for item in previous} == set(samples)
    updated = client.put(root + "/employment/" + entries["employment"]["id"], json={
        "details": {**samples["employment"], "position": "Manager"},
        "expected_version": 1})
    assert updated.status_code == 200
    second = client.post(drafts)
    assert second.status_code == 201
    prior_record = next(x for x in first.json()["history_snapshot"]["records"]
                        if x["kind"] == "employment")
    newer_record = next(x for x in second.json()["history_snapshot"]["records"]
                        if x["kind"] == "employment")
    assert prior_record["details"]["position"] == "Tester"
    assert newer_record["details"]["position"] == "Manager"
    assert prior_record["version"] == 1 and newer_record["version"] == 2
    assert client.get(drafts).json()[1]["history_snapshot"] == first.json()["history_snapshot"]
    summary = client.get(f"/api/v1/orgs/{org}/cases/{case}/history-evidence-review")
    assert summary.status_code == 200
    assert summary.json()["all_histories_verified"] is False
    assert summary.json()["official_form_generation_allowed"] is False
    assert all(field["status"] == "not_evidence_reviewed" for row in
               summary.json()["records"] for field in row["fields"])


def test_histories_same_firm_client_scope_and_other_firm(api):
    client, who, factory = api
    org, case, cid, root = context(api, "history-security")
    record = client.post(root + "/travel", json={"details": {
        "start_date": "2025-01-01", "purpose": "Synthetic visit",
        "destination_country": "Sample Republic"}}).json()
    other_cid = new_client(client, org)
    other_root = f"/api/v1/orgs/{org}/clients/{other_cid}/histories"
    assert client.put(other_root + "/travel/" + record["id"], json={
        "details": record["details"], "expected_version": 1}).status_code == 404
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="unassigned-consultant",
                          role="consultant", is_active=True))
        db.commit()
    who["sub"] = "unassigned-consultant"
    assert client.get(root).status_code == 404
    assert client.post(root + "/travel", json={"details": record["details"]}).status_code == 404
    assert client.get(f"/api/v1/orgs/{org}/cases/{case}/history-evidence-review").status_code == 404
    who["sub"] = "separate-owner"
    other_org = new_org(client, "history-other-firm")
    foreign_client = new_client(client, other_org)
    foreign = f"/api/v1/orgs/{other_org}/clients/{foreign_client}/histories"
    assert client.get(foreign).json()["records"] == []
    assert client.put(foreign + "/travel/" + record["id"], json={
        "details": record["details"], "expected_version": 1}).status_code == 404
