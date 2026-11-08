"""Staff-only intake worklist combines existing profile, case and intake layers."""
from uuid import UUID, uuid4

from app import study_intake_worklist as worklist
from app.models import CaseDocument, CaseFact, Membership
from tests.test_application_package import case_setup, start


def setup(api, slug, *, inside=False):
    client, _, _ = api
    org, case, root = case_setup(api, slug)
    result = start(client, root, representative=False,
                   context="inside_canada" if inside else "outside_canada")
    assert result.status_code == 201, result.text
    cid = next(x["client_id"] for x in client.get(
        f"/api/v1/orgs/{org}/cases").json() if x["id"] == case)
    return org, case, cid, f"/api/v1/orgs/{org}/cases/{case}/study-intake/worklist"


def test_worklist_exposes_missing_questions_without_values(api):
    client, _, _ = api
    org, case, cid, url = setup(api, "intake-worklist-empty")
    result = client.get(url)
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    body = result.json()
    assert body["form_code"] == "IMM1294"
    assert body["preliminary_question_count"] == 18
    assert body["document_verified_question_count"] == 0
    assert len(body["questions_still_requiring_evidence_or_review"]) == 18
    assert {q["status"] for q in body["questions"]} == {"missing_answer", "conditional_applicability_unresolved"}
    assert body["official_pdf_autofill_supported"] is False
    assert all("value" not in row for row in body["questions"])


def test_reusable_profile_is_not_misrepresented_as_verified(api):
    client, _, _ = api
    org, case, cid, url = setup(api, "intake-worklist-profile", inside=True)
    profile = f"/api/v1/orgs/{org}/clients/{cid}/applicant"
    assert client.put(profile, json={"identity": {
        "given_name": "Synthetic", "family_name": "Person"}}).status_code == 200
    data = client.get(url).json()
    assert data["form_code"] == "IMM5709"
    assert data["profile_version"] == 1
    name = next(x for x in data["questions"] if x["path"] == "identity.given_name")
    assert name["status"] == "reusable_profile_claim_needs_evidence"
    assert name["has_profile_claim"] is True
    assert data["document_verified_question_count"] == 0
    assert "Synthetic" not in str(data["questions"])


def test_verified_evidence_requires_cleared_scan(api, monkeypatch):
    client, _, factory = api
    org, case, cid, url = setup(api, "intake-worklist-evidence")
    doc_id = uuid4()
    with factory() as db:
        db.add(CaseDocument(
            id=doc_id, org_id=UUID(org), case_id=UUID(case),
            filename="test.pdf", document_type="passport", mime_type="application/pdf",
            size_bytes=100, sha256="c" * 64, storage_key=uuid4().hex,
            uploaded_by_sub="test-user-a"))
        db.add(CaseFact(
            org_id=UUID(org), case_id=UUID(case), document_id=doc_id,
            field_path="identity.given_name", value="Synthetic",
            review_status="verified", reviewed_by_sub="test-user-a",
            created_by_sub="test-user-a"))
        db.commit()
    blocked = client.get(url).json()
    name = next(x for x in blocked["questions"] if x["path"] == "identity.given_name")
    assert name["status"] == "evidence_review_required"
    assert blocked["document_verified_question_count"] == 0
    monkeypatch.setattr(worklist, "scan_status_by_document",
                        lambda *args: {doc_id: "cleared"})
    ready = client.get(url).json()
    name = next(x for x in ready["questions"] if x["path"] == "identity.given_name")
    assert name["status"] == "evidence_verified"
    assert ready["document_verified_question_count"] == 1


def test_member_without_case_assignment_cannot_read_worklist(api):
    client, who, factory = api
    org, case, cid, url = setup(api, "intake-worklist-access")
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="unassigned-consultant",
                          role="consultant", is_active=True))
        db.commit()
    who["sub"] = "unassigned-consultant"
    assert client.get(url).status_code == 404
    who["sub"] = "unrelated-user"
    assert client.get(url).status_code == 404


def test_conditional_refusal_followup_is_unknown_until_answer_and_not_assumed_no(api):
    from app.study_intake import QUESTION_BY_PATH
    client, _, _ = api
    org, case, cid, url = setup(api, "intake-conditional-unresolved")
    result = client.get(url).json()
    detail = next(q for q in result["questions"]
                  if q["path"] == "history.prior_refusal_details")
    assert detail["condition_state"] == "unresolved"
    assert detail["status"] == "conditional_applicability_unresolved"
    assert QUESTION_BY_PATH["history.prior_refusal_details"].condition_value == "yes"
