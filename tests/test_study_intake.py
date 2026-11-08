"""Study-permit questionnaire security and review tests (synthetic data only)."""
from uuid import UUID

from sqlalchemy import select

from app.intake_models import StudyIntakeDecision, StudyIntakeSubmission
from app.models import AuditEvent, CaseFact, Membership
from tests.test_portal import case_with_email, claim, invite


SYNTHETIC_ANSWERS = {
    "identity.given_name": "Avery",
    "identity.family_name": "Sample",
    "identity.date_of_birth": "2001-01-02",
    "identity.citizenship": "Fictionland",
    "identity.passport_number": "FICTIONAL-PASSPORT",
    "education.institution": "Test College",
    "education.program_start_date": "2027-09-01",
    "education.program_end_date": "2029-06-01",
    "finance.tuition_cad": "25000",
    "finance.expenses_paid_by": "parents",
    "history.prior_refusal": "unsure",
}


def _client_url(case_id):
    return f"/api/v1/client/cases/{case_id}/study-intake"


def _staff_url(org, case_id):
    return f"/api/v1/orgs/{org}/cases/{case_id}/study-intake"


def _open_client(api, name="questionnaire"):
    client, who, factory = api
    org, case = case_with_email(api, name)
    staff = who["sub"]
    inv = invite(client, org, case)
    assert claim(client, who, inv["invite_token"],
                 sub=name + "-client", email="sample.person@example.test").status_code == 200
    return org, case, staff


def _submit(client, case, fields=None, acknowledged=True, version=None):
    template = client.get(_client_url(case)).json()
    return client.post(_client_url(case) + "/submissions", json={
        "template_version": version or template["template_version"],
        "acknowledged_notice": acknowledged,
        "answers": fields if fields is not None else SYNTHETIC_ANSWERS,
    })


def test_client_questionnaire_and_validation(api):
    client, who, factory = api
    org, case, staff = _open_client(api, "questionnaire-validation")
    schema = client.get(_client_url(case))
    assert schema.status_code == 200, schema.text
    assert schema.json()["not_official_ircc_form"] is True
    assert schema.json()["submission_supported"] is False
    assert len(schema.json()["fields"]) >= 15
    assert _submit(client, case, acknowledged=False).status_code == 422
    assert _submit(client, case, version="obsolete-version").status_code == 409
    assert _submit(client, case, fields={"identity.given_name": "Avery"}).status_code == 422
    assert _submit(client, case, fields={**SYNTHETIC_ANSWERS,
                   "unsupported.private_field": "secret"}).status_code == 422
    assert _submit(client, case, fields={**SYNTHETIC_ANSWERS,
                   "history.prior_refusal": "definitely"}).status_code == 422
    assert _submit(client, case, fields={**SYNTHETIC_ANSWERS,
                   "identity.date_of_birth": "2026-99-99"}).status_code == 422
    assert _submit(client, case, fields={**SYNTHETIC_ANSWERS,
                   "finance.tuition_cad": "-40"}).status_code == 422
    saved = _submit(client, case)
    assert saved.status_code == 201, saved.text
    assert saved.json()["review_status"] == "awaiting_staff_review"
    assert client.get(_client_url(case)).json()["last_submission_id"] == saved.json()["id"]
    with factory() as db:
        row = db.scalar(select(StudyIntakeSubmission).where(
            StudyIntakeSubmission.id == UUID(saved.json()["id"])))
        assert row.answers["identity.passport_number"] == "FICTIONAL-PASSPORT"
        audit = db.scalar(select(AuditEvent).where(
            AuditEvent.action == "portal.study_intake_submitted"))
        assert audit is not None
        assert "FICTIONAL-PASSPORT" not in str(audit.details)
        assert audit.details["answer_count"] == len(SYNTHETIC_ANSWERS)


def test_staff_can_accept_only_latest_and_fact_stays_unverified(api):
    client, who, factory = api
    org, case, staff = _open_client(api, "questionnaire-staff")
    first = _submit(client, case)
    assert first.status_code == 201, first.text
    who["sub"] = staff
    path = _staff_url(org, case)
    listed = client.get(path)
    assert listed.status_code == 200, listed.text
    assert listed.json()["submissions"][0]["answers"]["identity.given_name"] == "Avery"
    response = client.post(path + f"/{first.json()['id']}/answers/identity.given_name/decide",
                           json={"decision": "accept"})
    assert response.status_code == 201, response.text
    fact_id = response.json()["created_fact_id"]
    assert response.json()["fact_status"] == "pending"
    facts = client.get(f"/api/v1/orgs/{org}/cases/{case}/facts").json()
    matched = next(f for f in facts if f["id"] == fact_id)
    assert matched["review_status"] == "pending"
    assert matched["document_id"] is None
    assert first.json()["id"] in matched["source_excerpt"]
    assert client.post(path + f"/{first.json()['id']}/answers/identity.given_name/decide",
                       json={"decision": "accept"}).status_code == 409
    dismissed = client.post(path + f"/{first.json()['id']}/answers/history.prior_refusal/decide",
                            json={"decision": "dismiss"})
    assert dismissed.status_code == 201
    assert dismissed.json()["created_fact_id"] is None
    assert client.get(path).json()["submissions"][0]["decisions"]
    with factory() as db:
        assert db.scalar(select(StudyIntakeDecision).where(
            StudyIntakeDecision.created_fact_id == UUID(fact_id))) is not None


def test_old_submission_requires_fresh_review_and_no_silent_overwrite(api):
    client, who, factory = api
    org, case, staff = _open_client(api, "questionnaire-revision")
    first = _submit(client, case)
    second = _submit(client, case, fields={**SYNTHETIC_ANSWERS,
                                         "identity.given_name": "Different"})
    assert first.status_code == 201 and second.status_code == 201
    who["sub"] = staff
    path = _staff_url(org, case)
    listing = client.get(path).json()
    assert listing["current_submission_id"] == second.json()["id"]
    assert len(listing["submissions"]) == 2
    assert client.post(path + f"/{first.json()['id']}/answers/identity.given_name/decide",
                       json={"decision": "accept"}).status_code == 409
    assert client.post(path + f"/{second.json()['id']}/answers/identity.given_name/decide",
                       json={"decision": "accept"}).status_code == 201
    assert client.post(path + f"/{second.json()['id']}/answers/no.such_field/decide",
                       json={"decision": "accept"}).status_code == 404


def test_case_grants_revocation_and_staff_roles(api):
    client, who, factory = api
    org, case, staff = _open_client(api, "questionnaire-revoke")
    assert _submit(client, case).status_code == 201
    # Staff sees case data, but mere firm viewer cannot ingest an answer.
    who["sub"] = staff
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="junior-reviewer",
                          role="assistant", is_active=True))
        db.commit()
    who["sub"] = "junior-reviewer"
    path = _staff_url(org, case)
    listing = client.get(path)
    assert listing.status_code == 404  # Firm membership alone grants no case access.
    # No assistant case grant exists, so signoff is also inaccessible.
    assert client.post(path + "/00000000-0000-4000-8000-000000000001/answers/identity.family_name/decide",
                       json={"decision": "accept"}).status_code == 404
    who["sub"] = "not-a-member"
    assert client.get(path).status_code == 404
    who["sub"] = staff
    grants = client.get(f"/api/v1/orgs/{org}/cases/{case}/portal/grants").json()
    assert len(grants) == 1
    assert client.post(f"/api/v1/orgs/{org}/cases/{case}/portal/grants/{grants[0]['id']}/revoke").status_code == 200
    who.update(sub="questionnaire-revoke-client", email="sample.person@example.test",
               email_verified=True)
    assert client.get(_client_url(case)).status_code == 404
    assert client.post(_client_url(case) + "/submissions", json={
        "template_version": "study-permit-preliminary-intake-2026-11-06",
        "acknowledged_notice": True, "answers": SYNTHETIC_ANSWERS
    }).status_code == 404


def test_other_firm_case_is_hidden_even_with_valid_client_identity(api):
    client, who, factory = api
    org, case, staff = _open_client(api, "questionnaire-first")
    first_sub = _submit(client, case)
    assert first_sub.status_code == 201
    org2, case2 = case_with_email(api, "questionnaire-other")
    assert case2 != case
    # Separate staff account may not see another firm's questionnaire.
    assert client.get(_staff_url(org, case)).status_code == 404
    inv2 = invite(client, org2, case2)
    assert claim(client, who, inv2["invite_token"], sub="second-client",
                 email="sample.person@example.test").status_code == 200
    assert client.get(_client_url(case)).status_code == 404
    assert client.get(_client_url(case2)).status_code == 200


def test_client_submission_invalidates_preflight_and_evidence_review_fingerprint(api):
    client, who, factory = api
    org, case, staff = _open_client(api, "questionnaire-stale-review")
    who["sub"] = staff
    preflight = (f"/api/v1/orgs/{org}/ircc/cases/{case}/forms/IMM1294/"
                 "preflight?filing_context=outside_canada")
    review = (f"/api/v1/orgs/{org}/cases/{case}/reviews/current"
              "?filing_context=outside_canada")
    before_form = client.get(preflight)
    before_review = client.get(review)
    assert before_form.status_code == 200, before_form.text
    assert before_review.status_code == 200, before_review.text
    original_form_sha = before_form.json()["snapshot_sha256"]
    original_review_sha = before_review.json()["case_sha256"]

    who.update(sub="questionnaire-stale-review-client",
               email="sample.person@example.test", email_verified=True)
    saved = _submit(client, case)
    assert saved.status_code == 201, saved.text

    who.update(sub=staff, email=None, email_verified=False)
    after_form = client.get(preflight)
    after_review = client.get(review)
    assert after_form.status_code == 200, after_form.text
    assert after_review.status_code == 200, after_review.text
    assert after_form.json()["snapshot_sha256"] != original_form_sha
    assert after_review.json()["case_sha256"] != original_review_sha
    assert any("questionnaire answers await consultant decisions" in reason.lower()
               for reason in after_form.json()["blockers"])


def test_prior_refusal_requires_details_only_when_yes(api):
    from app.study_intake import validate_answers, questionnaire
    from fastapi import HTTPException
    schema = questionnaire()
    details = next(q for q in schema["fields"]
                   if q["path"] == "history.prior_refusal_details")
    assert details["condition_path"] == "history.prior_refusal"
    assert details["condition_value"] == "yes"
    assert details["required"] is True
    yes = {**SYNTHETIC_ANSWERS, "history.prior_refusal": "yes"}
    try:
        validate_answers(yes)
        assert False, "A prior refusal with no details cannot be accepted"
    except HTTPException as exc:
        assert exc.status_code == 422
    accepted = validate_answers({
        **yes, "history.prior_refusal_details": "Fictional refusal in 2023"})
    assert accepted["history.prior_refusal_details"] == "Fictional refusal in 2023"
    for answer in ("no", "unsure"):
        try:
            validate_answers({
                **SYNTHETIC_ANSWERS, "history.prior_refusal": answer,
                "history.prior_refusal_details": "Stale hidden detail"})
            assert False, "Hidden details must not survive a condition change"
        except HTTPException as exc:
            assert exc.status_code == 422
    assert "history.prior_refusal_details" not in validate_answers(SYNTHETIC_ANSWERS)


def test_versioned_client_conditional_submission_and_review(api):
    client, who, factory = api
    org, case, staff = _open_client(api, "questionnaire-condition")
    yes = {**SYNTHETIC_ANSWERS, "history.prior_refusal": "yes"}
    assert _submit(client, case, fields=yes).status_code == 422
    saved = _submit(client, case, fields={
        **yes, "history.prior_refusal_details": "Fictional permit refused in 2024"})
    assert saved.status_code == 201, saved.text
    who["sub"] = staff
    staff_url = _staff_url(org, case)
    result = client.post(
        staff_url + f"/{saved.json()['id']}/answers/history.prior_refusal_details/decide",
        json={"decision": "accept"})
    assert result.status_code == 201, result.text
    assert result.json()["fact_status"] == "pending"
