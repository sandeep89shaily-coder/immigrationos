"""RCIC study-permit planning never converts received documents into approvals."""
from uuid import UUID, uuid4

from app.models import CaseDocument, CaseFact, CaseIssue, Membership
from app.portal_models import DocumentRequest, PortalSubmission
from tests.test_api import new_client, new_org


def setup_case(api, slug="rcic-evidence", application_type="study_permit"):
    client, _, _ = api
    org = new_org(client, slug)
    person = new_client(client, org)
    resp = client.post(f"/api/v1/orgs/{org}/cases", json={
        "client_id": person, "application_type": application_type, "title": "Fictional case"})
    assert resp.status_code == 201, resp.text
    return org, resp.json()["id"]


def test_default_matrix_is_non_exhaustive_and_never_submission_ready(api):
    client, _, _ = api
    org, case = setup_case(api)
    endpoint = f"/api/v1/orgs/{org}/cases/{case}/evidence/matrix?filing_context=outside_canada"
    r = client.get(endpoint)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["release_status"] == "review_only_no_ircc_submission"
    assert body["professional_review_required"] is True
    by_key = {item["key"]: item for item in body["requirements"]}
    assert by_key["passport"]["status"] == "missing"
    assert by_key["identity_facts"]["status"] == "unverified"
    assert by_key["pal_tal"]["requires_professional_applicability_review"] is True
    assert "canada.ca" in by_key["financial_support"]["source_url"]
    assert client.get(endpoint.replace("outside_canada", "unknown")).status_code == 422


def test_requests_create_once_and_never_send_client_messages(api):
    client, _, _ = api
    org, case = setup_case(api, "request-once")
    root = f"/api/v1/orgs/{org}/cases/{case}/evidence"
    first = client.post(root + "/request-missing", json={"filing_context": "inside_canada"})
    assert first.status_code == 200, first.text
    assert {x["requirement_key"] for x in first.json()["created"]} == {
        "passport", "letter_of_acceptance", "financial_support", "pal_tal"}
    assert first.json()["no_client_message_sent"] is True
    retry = client.post(root + "/request-missing", json={"filing_context": "inside_canada"})
    assert retry.status_code == 200 and retry.json()["created"] == []
    matrix = client.get(root + "/matrix?filing_context=inside_canada").json()
    assert {x["status"] for x in matrix["requirements"] if x["kind"] != "verified_facts"} == {"requested"}
    assert client.post(root + "/request-missing", json={"filing_context": "inside_canada",
        "requirement_keys": ["passport", "passport"]}).status_code == 422
    assert client.post(root + "/request-missing", json={"filing_context": "inside_canada",
        "requirement_keys": ["not_a_requirement"]}).status_code == 422


def test_quarantined_portal_evidence_is_never_received_for_review(api):
    client, _, factory = api
    org, case = setup_case(api, "quarantined-evidence")
    with factory() as db:
        req = DocumentRequest(org_id=UUID(org), case_id=UUID(case), title="Passport", instructions="Fictional",
                              document_type="passport", status="received", created_by_sub="staff")
        doc = CaseDocument(org_id=UUID(org), case_id=UUID(case), filename="fake.pdf", document_type="passport",
                           mime_type="application/pdf", size_bytes=100, sha256="0" * 64,
                           storage_key=str(uuid4()), uploaded_by_sub="client")
        db.add_all([req, doc]); db.flush()
        db.add(PortalSubmission(org_id=UUID(org), case_id=UUID(case), request_id=req.id,
                                document_id=doc.id, uploaded_by_sub="client", scan_status="quarantined"))
        db.commit()
        did = doc.id
    url = f"/api/v1/orgs/{org}/cases/{case}/evidence/matrix?filing_context=outside_canada"
    item = next(x for x in client.get(url).json()["requirements"] if x["key"] == "passport")
    assert item["status"] == "quarantined" and item["document_ids"] == []
    with factory() as db:
        db.query(PortalSubmission).filter_by(document_id=did).update({"scan_status": "rejected"})
        db.commit()
    item = next(x for x in client.get(url).json()["requirements"] if x["key"] == "passport")
    assert item["status"] == "rejected_upload" and item["document_ids"] == []
    with factory() as db:
        db.query(PortalSubmission).filter_by(document_id=did).update({"scan_status": "cleared"})
        db.commit()
    item = next(x for x in client.get(url).json()["requirements"] if x["key"] == "passport")
    assert item["status"] == "received_for_review"
    assert item["document_ids"] == [str(did)]


def test_verified_facts_do_not_hide_conflicts_and_open_issues(api):
    client, _, factory = api
    org, case = setup_case(api, "verified-conflicts")
    with factory() as db:
        db.add_all([
            CaseFact(org_id=UUID(org), case_id=UUID(case), field_path="identity.given_name", value="A",
                     review_status="verified", created_by_sub="staff"),
            CaseFact(org_id=UUID(org), case_id=UUID(case), field_path="identity.given_name", value="B",
                     review_status="verified", created_by_sub="staff"),
            CaseIssue(org_id=UUID(org), case_id=UUID(case), field_path="identity.given_name", fingerprint="1"*64,
                      issue_type="conflicting_evidence", description="Conflicting values", status="open"),
        ])
        db.commit()
    url = f"/api/v1/orgs/{org}/cases/{case}/evidence/matrix?filing_context=outside_canada"
    data = client.get(url).json()
    item = next(x for x in data["requirements"] if x["key"] == "identity_facts")
    assert item["status"] == "conflict"
    assert data["open_evidence_issue_count"] == 1


def test_tenant_role_closed_and_unsupported_case_guards(api):
    client, who, factory = api
    org, case = setup_case(api, "access-evidence")
    root = f"/api/v1/orgs/{org}/cases/{case}/evidence"
    who["sub"] = "outsider"
    assert client.get(root + "/matrix?filing_context=inside_canada").status_code == 404
    assert client.post(root + "/request-missing", json={"filing_context": "inside_canada"}).status_code == 404
    who["sub"] = "viewer"
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="viewer", role="viewer", is_active=True));db.commit()
    assert client.get(root + "/matrix?filing_context=inside_canada").status_code == 404
    assert client.post(root + "/request-missing", json={"filing_context": "inside_canada"}).status_code == 404
    who["sub"] = "test-user-a"
    client.patch(f"/api/v1/orgs/{org}/cases/{case}/status", json={"status": "closed", "reason": "Synthetic case complete"})
    assert client.post(root + "/request-missing", json={"filing_context": "inside_canada"}).status_code == 409
    _, other = setup_case(api, "unsupported-evidence", application_type="work_permit")
    assert client.get(f"/api/v1/orgs/{org}/cases/{other}/evidence/matrix?filing_context=inside_canada").status_code == 404
