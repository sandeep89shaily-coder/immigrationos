"""Case-specific source-pinned document review tests; synthetic data only."""
from uuid import UUID, uuid4
from sqlalchemy.exc import IntegrityError
import pytest

from tests.test_application_package import case_setup, start
from app.models import CaseDocument, Membership
from app.requirement_models import RequirementDecision


REASON = "Consultant reviewed the fictional circumstances against current source instructions."


def setup(api, slug="requirements-demo"):
    client, _, _ = api
    org, case, pkg = case_setup(api, slug)
    assert start(client, pkg, representative=False).status_code == 201
    return org, case, f"/api/v1/orgs/{org}/cases/{case}/requirements"


def doc(api, org, case, kind="passport"):
    _, _, factory = api
    record = CaseDocument(org_id=UUID(org), case_id=UUID(case),
        filename="synthetic-test.pdf", document_type=kind,
        mime_type="application/pdf", size_bytes=14, sha256="a" * 64,
        storage_key=uuid4().hex, uploaded_by_sub="test-user-a")
    with factory() as db:
        db.add(record); db.commit()
    return str(record.id)


def test_conditional_applicability_is_versioned_and_required_entries_cannot_be_exempted(api):
    client, _, factory = api
    org, case, root = setup(api, "requirements-conditional")
    initial = client.get(root)
    assert initial.status_code == 200, initial.text
    checklist = initial.json()
    assert checklist["official_application_ready"] is False
    rows = {r["key"]: r for r in checklist["requirements"]}
    assert rows["pal_tal"]["applicability"] == "review_required"
    assert rows["passport"]["applicability"] == "required"
    payload = {"decision": "not_applicable", "reason": REASON,
               "confirmed_current_source": True, "expected_revision": 0}
    assert client.post(root + "/passport/applicability", json=payload).status_code == 409
    assert client.post(root + "/pal_tal/applicability", json={
        **payload, "confirmed_current_source": False}).status_code == 422
    decided = client.post(root + "/pal_tal/applicability", json=payload)
    assert decided.status_code == 201, decided.text
    assert decided.json()["revision"] == 1
    assert decided.json()["source_observed_on"]
    assert client.post(root + "/pal_tal/applicability", json=payload).status_code == 409
    item = next(r for r in client.get(root).json()["requirements"] if r["key"] == "pal_tal")
    assert item["status"] == "professionally_marked_not_applicable"
    changed = client.post(root + "/pal_tal/applicability", json={
        **payload, "decision": "required", "expected_revision": 1})
    assert changed.status_code == 201
    assert changed.json()["revision"] == 2
    assert next(r for r in client.get(root).json()["requirements"]
                if r["key"] == "pal_tal")["applicability"] == "required"
    with factory() as db:
        assert [x.revision for x in db.query(RequirementDecision).order_by(
            RequirementDecision.revision).all()] == [1, 2]


def test_document_review_is_bound_to_correct_case_and_type(api):
    client, _, _ = api
    org, case, root = setup(api, "requirements-review")
    password = doc(api, org, case, "passport")
    url = root + "/passport/documents/review"
    data = {"document_id": password, "decision": "accepted",
            "reason": REASON, "inspected_original_document": True}
    assert client.post(url, json={**data, "inspected_original_document": False}).status_code == 422
    assert client.post(root + "/financial_support/documents/review", json=data).status_code == 409
    good = client.post(url, json=data)
    assert good.status_code == 201, good.text
    assert good.json()["document_sha256"] == "a" * 64
    assert client.post(url, json=data).status_code == 409
    passport = next(r for r in client.get(root).json()["requirements"]
                    if r["key"] == "passport")
    assert passport["status"] == "staff_reviewed_document"
    assert passport["reviewed_document_ids"] == [password]
    assert client.get(root).json()["official_application_ready"] is False
    client2 = client.post(f"/api/v1/orgs/{org}/clients", json={
        "first_name": "Demo", "last_name": "Other"}).json()["id"]
    other = client.post(f"/api/v1/orgs/{org}/cases", json={
        "client_id": client2, "title": "Other case", "application_type": "study_permit"}).json()["id"]
    foreign = doc(api, org, other, "passport")
    assert client.post(url, json={**data, "document_id": foreign}).status_code == 404


def test_requirement_access_restricted_to_assigned_cases(api):
    client, who, factory = api
    org, case, root = setup(api, "requirements-access")
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="unassigned-consultant",
                          role="consultant", is_active=True))
        db.commit()
    who["sub"] = "unassigned-consultant"
    assert client.get(root).status_code == 404
    assert client.post(root + "/pal_tal/applicability", json={
        "decision": "not_applicable", "reason": REASON,
        "confirmed_current_source": True, "expected_revision": 0}).status_code == 404
    who["sub"] = "outside"
    assert client.get(root).status_code == 404
