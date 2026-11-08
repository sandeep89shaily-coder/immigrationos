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
    assert body["preliminary_question_count"] == 39
    assert body["document_verified_question_count"] == 0
    assert len(body["questions_still_requiring_evidence_or_review"]) == 39
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


def test_alias_national_id_and_expense_payer_conditions_reach_worklist(api):
    from app.intake_models import StudyIntakeSubmission
    from app.study_intake import TEMPLATE_VERSION
    from uuid import uuid4
    client, _, factory = api
    org, case, cid, url = setup(api, "expanded-condition-worklist")
    with factory() as db:
        db.add(StudyIntakeSubmission(
            id=uuid4(), org_id=UUID(org), case_id=UUID(case),
            created_by_sub="fictional-client",
            template_version=TEMPLATE_VERSION, notice_version="test",
            answer_sha256="a"*64,
            answers={"identity.has_other_names":"no",
                     "identity.has_national_id":"yes",
                     "finance.expenses_paid_by":"other"}))
        db.commit()
    data = client.get(url).json()
    states = {r["path"]: r for r in data["questions"]}
    assert states["identity.other_family_name"]["status"] == "not_applicable_to_latest_answer"
    assert states["identity.national_id_number"]["condition_state"] == "active"
    assert states["finance.expenses_payer_details"]["status"] == "missing_answer"
    assert data["preliminary_question_count"] == 39
    assert data["official_form_complete"] is False


def test_employment_lookback_is_explicit_and_never_certifies_completeness(api):
    from datetime import date
    client, _, _ = api
    org, case, cid, url = setup(api, "occupation-history-ten-year-gap")
    result = client.get(url)
    assert result.status_code == 200, result.text
    review = result.json()["employment_history_review"]
    assert review["record_count"] == 0
    assert review["flag_types"] == ["uncovered_period_for_review"]
    assert review["window_end"] == date.today().isoformat()
    assert review["verified_complete"] is False
    assert review["retirement_exception_assessed"] is False
    assert "canada.ca" in review["source_url"]
    assert result.json()["official_form_complete"] is False


def test_unknown_employment_end_is_not_treated_as_current(api):
    client, _, _ = api
    org, case, cid, url = setup(api, "occupation-history-unknown-end")
    created=client.post(f"/api/v1/orgs/{org}/clients/{cid}/histories/employment",
        json={"details":{"start_date":"2020-01-01","employer":"Imaginary Company",
                         "position":"Tester","country":"Fictionland",
                         "employment_status":"employed"}})
    assert created.status_code == 201, created.text
    review=client.get(url).json()["employment_history_review"]
    assert "end_date_not_supplied" in review["flag_types"]
    assert "uncovered_period_for_review" not in review["flag_types"]
    assert review["coverage_evaluable"] is False
    assert review["verified_complete"] is False


def test_supplemental_crosscheck_disclosure_and_accepted_history_lacks_evidence(api):
    from app.intake_models import StudyIntakeSubmission
    from app.applicant_supplemental_history_models import ApplicantSupplementalHistory
    from app.repeatable_intake_models import ClientRepeatableProposal, ClientRepeatableDecision
    from app.study_intake import TEMPLATE_VERSION
    client, _, factory = api
    org, case, cid, url = setup(api, "supplemental-disclosure-missing-evidence")
    oid, caseid, clientid = UUID(org), UUID(case), UUID(cid)
    proposal_id = uuid4()
    supplemental_id = uuid4()
    with factory() as db:
        db.add(StudyIntakeSubmission(
            org_id=oid, case_id=caseid, created_by_sub="fictional-portal",
            template_version=TEMPLATE_VERSION, notice_version="test",
            answer_sha256="a"*64,
            answers={"history.has_previous_relationships":"yes",
                     "history.has_foreign_residences":"no"}))
        db.add(ClientRepeatableProposal(
            id=proposal_id, org_id=oid, case_id=caseid,
            kind="previous_relationship",
            details={"relationship_type":"married","given_name":"Prior",
                     "family_name":"Fiction","start_date":"2010-01-01",
                     "end_date":"2015-01-01"},
            content_sha256="b"*64, template_version="repeatable-test",
            notice_version="test", created_by_sub="fictional-portal"))
        db.add(ClientRepeatableDecision(
            org_id=oid, case_id=caseid, proposal_id=proposal_id,
            decision="accept", created_record_id=supplemental_id,
            reviewed_by_sub="test-owner"))
        db.add(ApplicantSupplementalHistory(
            id=supplemental_id, org_id=oid, client_id=clientid,
            kind="previous_relationship",
            details={"relationship_type":"married","given_name":"Prior",
                     "family_name":"Fiction","start_date":"2010-01-01",
                     "end_date":"2015-01-01"},
            updated_by_sub="test-owner"))
        db.commit()
    result = client.get(url)
    assert result.status_code == 200, result.text
    checks = {r["kind"]:r for r in result.json()["supplemental_disclosure_review"]}
    relationship = checks["previous_relationship"]
    assert relationship["status"]=="supplemental_evidence_review_required"
    assert relationship["accepted_record_ids"]==[str(supplemental_id)]
    assert relationship["evidence"][0]["verified_required_field_count"]==0
    assert relationship["evidence"][0]["record_is_professionally_verified"] is False
    assert checks["foreign_residence"]["status"]=="no_disclosure_reported"
    assert "Fiction" not in str(checks)
    assert result.json()["official_form_complete"] is False


def test_supplemental_pending_proposal_and_no_declaration_disagreement(api):
    from app.intake_models import StudyIntakeSubmission
    from app.repeatable_intake_models import ClientRepeatableProposal
    from app.study_intake import TEMPLATE_VERSION
    client, _, factory = api
    org, case, cid, url = setup(api, "supplemental-disclosure-pending-conflict")
    oid, caseid = UUID(org), UUID(case)
    proposal_id = uuid4()
    with factory() as db:
        db.add(StudyIntakeSubmission(
            org_id=oid, case_id=caseid, created_by_sub="fictional-portal",
            template_version=TEMPLATE_VERSION, notice_version="test",
            answer_sha256="c"*64,
            answers={"history.has_previous_relationships":"no",
                     "history.has_foreign_residences":"yes"}))
        db.add(ClientRepeatableProposal(
            id=proposal_id, org_id=oid, case_id=caseid,
            kind="previous_relationship",
            details={"relationship_type":"married","given_name":"Historical",
                     "family_name":"Example","start_date":"2010-01-01",
                     "end_date":"2015-01-01"},
            content_sha256="d"*64, template_version="repeatable-test",
            notice_version="test", created_by_sub="fictional-portal"))
        db.commit()
    out = client.get(url)
    assert out.status_code == 200, out.text
    checks={r["kind"]:r for r in out.json()["supplemental_disclosure_review"]}
    assert checks["previous_relationship"]["status"]=="disclosure_conflict_review_required"
    assert checks["previous_relationship"]["pending_proposal_ids"]==[str(proposal_id)]
    assert checks["foreign_residence"]["status"]=="missing_repeatable_records"
    assert checks["foreign_residence"]["ircc_form_section_complete"] is False
