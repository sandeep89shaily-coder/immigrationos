"""IMM5476 preparation is evidence-backed and read-only, never an official PDF."""
from uuid import UUID, uuid4

from app import imm5476_case_preview as preview
from app.models import Case, CaseDocument, CaseFact, CaseIssue, Membership
from tests.test_application_package import case_setup


def path(org, case):
    return f"/api/v1/orgs/{org}/cases/{case}/ircc/IMM5476/preparation"


def make_case(api, slug):
    org, case, _ = case_setup(api, slug)
    return org, case, path(org, case)


def add_source_and_facts(api, org, case, *, all_fields=True, status="verified"):
    _, _, factory = api
    doc_id = uuid4()
    with factory() as db:
        db.add(CaseDocument(
            id=doc_id, org_id=UUID(org), case_id=UUID(case),
            filename="fictional-evidence.pdf", document_type="identity",
            mime_type="application/pdf", size_bytes=100,
            sha256="b" * 64, storage_key=uuid4().hex,
            uploaded_by_sub="test-user-a"))
        for index, (key, canonical) in enumerate(preview.CANONICAL_FIELDS.items()):
            if index == 20 and not all_fields:
                continue
            db.add(CaseFact(
                org_id=UUID(org), case_id=UUID(case),
                document_id=doc_id, field_path=canonical,
                value={
                    "applicant_dob": "2001-06-09",
                    "applicant_email": "applicant@example.test",
                    "representative_email": "representative@example.test",
                    "uci": "1234-5678",
                }.get(key, "Synthetic-" + key), review_status=status,
                created_by_sub="test-user-a",
                reviewed_by_sub="test-user-a" if status == "verified" else None))
        db.commit()
    return doc_id


def test_missing_case_evidence_has_21_explicit_gaps_and_no_export(api):
    client, _, _ = api
    org, case, url = make_case(api, "imm5476-review-missing")
    r = client.get(url)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    data = r.json()
    assert data["form_code"] == "IMM5476"
    assert data["revision"] == "11-2025"
    assert data["operation"] == "appoint"
    assert data["representative_type"] == "paid_cicc"
    assert data["observed_text_fields"] == 21
    assert data["verified_text_fields"] == 0
    assert len(data["fields"]) == 21
    assert {x["status"] for x in data["fields"]} == {"missing_evidence"}
    assert {x["value"] for x in data["fields"]} == {None}
    assert "observed_fields_unresolved" in data["blockers"]
    assert "commercial_pdf_engine_licence_unverified" in data["blockers"]
    assert data["verified_observed_subset"] is False
    assert data["verified_source_fingerprint"] is None
    assert data["pdf_export_available"] is False
    assert data["official_pdf_autofill_supported"] is False
    assert data["official_ircc_validation_verified"] is False
    assert data["submission_supported"] is False


def test_completed_scanned_reviewed_subset_has_provenance_but_still_no_pdf(api, monkeypatch):
    client, _, factory = api
    org, case, url = make_case(api, "imm5476-review-complete")
    doc_id = add_source_and_facts(api, org, case)
    monkeypatch.setattr(preview, "scan_status_by_document",
                        lambda *args: {doc_id: "cleared"})
    r = client.get(url)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["verified_text_fields"] == 21
    assert data["verified_observed_subset"] is True
    assert len(data["verified_source_fingerprint"]) == 64
    assert "observed_fields_unresolved" not in data["blockers"]
    assert data["pdf_export_available"] is False
    assert data["submission_supported"] is False
    for field in data["fields"]:
        assert field["value"] == {
            "applicant_dob": "2001-06-09",
            "applicant_email": "applicant@example.test",
            "representative_email": "representative@example.test",
            "uci": "1234-5678",
        }.get(field["key"], "Synthetic-" + field["key"])
        assert field["status"] == "verified_source_value"
        assert field["source_hashes"] == ["b" * 64]
        assert field["document_ids"] == [str(doc_id)]
        assert len(field["evidence_ids"]) == 1
        assert field["observed_pdf_field"].startswith("IMM_5476[0].Page1[0].")
    assert client.get(url).json()["snapshot_sha256"] == data["snapshot_sha256"]
    # Case evidence changes must invalidate the previous snapshot immediately.
    with factory() as db:
        fact = db.query(CaseFact).filter(
            CaseFact.case_id == UUID(case),
            CaseFact.field_path == "identity.given_name").first()
        fact.value = "New-reviewed-synthetic-value"
        db.commit()
    after = client.get(url).json()
    assert after["snapshot_sha256"] != data["snapshot_sha256"]
    assert after["verified_source_fingerprint"] != data["verified_source_fingerprint"]


def test_even_verified_fields_fail_closed_without_document_scan(api, monkeypatch):
    client, _, factory = api
    org, case, url = make_case(api, "imm5476-review-scan")
    doc_id = add_source_and_facts(api, org, case)
    response = client.get(url).json()
    assert response["verified_text_fields"] == 0
    assert {x["status"] for x in response["fields"]} == {"source_scan_not_cleared"}
    assert all(x["value"] is None for x in response["fields"])
    for state in ("rejected", "quarantined"):
        monkeypatch.setattr(preview, "scan_status_by_document",
                            lambda *args, state=state: {doc_id: state})
        response = client.get(url).json()
        assert response["verified_text_fields"] == 0
        assert {x["status"] for x in response["fields"]} == {"source_scan_not_cleared"}


def test_unreviewed_conflicted_and_unlinked_sources_never_leak_values(api, monkeypatch):
    client, _, factory = api
    org, case, url = make_case(api, "imm5476-review-conflict")
    doc_id = add_source_and_facts(api, org, case)
    monkeypatch.setattr(preview, "scan_status_by_document",
                        lambda *args: {doc_id: "cleared"})
    with factory() as db:
        unreviewed = db.query(CaseFact).filter(
            CaseFact.case_id == UUID(case),
            CaseFact.field_path == "identity.given_name").first()
        unreviewed.review_status = "pending"
        unreviewed.reviewed_by_sub = None
        conflicting = db.query(CaseFact).filter(
            CaseFact.case_id == UUID(case),
            CaseFact.field_path == "identity.family_name").first()
        db.add(CaseFact(org_id=UUID(org), case_id=UUID(case),
                        document_id=doc_id, field_path=conflicting.field_path,
                        value="Contradictory synthetic surname", review_status="verified",
                        created_by_sub="test-user-a", reviewed_by_sub="test-user-a"))
        # The representative's source is deliberately unlinked.
        unlinked = db.query(CaseFact).filter(
            CaseFact.case_id == UUID(case),
            CaseFact.field_path == "representative.given_name").first()
        unlinked.document_id = None
        db.commit()
    data = client.get(url).json()
    by_key = {f["key"]: f for f in data["fields"]}
    for key, expected in [
        ("applicant_given", "unreviewed_evidence"),
        ("applicant_family", "conflicting_evidence"),
        ("representative_given", "missing_case_document"),
    ]:
        assert by_key[key]["status"] == expected
        assert by_key[key]["value"] is None
        assert by_key[key]["evidence_ids"] == []
    assert data["verified_observed_subset"] is False
    assert data["verified_source_fingerprint"] is None
    assert data["verified_text_fields"] == 18


def test_workflow_mismatch_and_unassigned_staff_are_denied(api):
    client, who, factory = api
    org, case, url = make_case(api, "imm5476-review-access")
    assert client.get(url + "?operation=cancel").status_code == 422
    assert client.get(url + "?representative_type=lawyer").status_code == 422
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="unassigned-viewer",
                          role="viewer", is_active=True))
        db.commit()
    who["sub"] = "unassigned-viewer"
    assert client.get(url).status_code == 404
    who["sub"] = "outsider"
    assert client.get(url).status_code == 404


def test_open_issues_closed_cases_and_source_age_gate_even_internal_preview(api):
    client, _, factory = api
    org, case, url = make_case(api, "imm5476-review-blockers")
    with factory() as db:
        obj = db.query(Case).filter(Case.id == UUID(case)).one()
        obj.status = "closed"
        db.add(CaseIssue(
            org_id=UUID(org), case_id=UUID(case),
            fingerprint="c" * 64, issue_type="inconsistent",
            field_path="identity.family_name", description="Fictional conflict",
            severity="review", status="open"))
        db.commit()
    result = client.get(url).json()
    assert "case_closed" in result["blockers"]
    assert "open_evidence_issues" in result["blockers"]
    assert result["open_evidence_issues"] == 1
    with factory() as db:
        obj = db.query(Case).filter(Case.id == UUID(case)).one()
        computed = preview.build_preview(
            org_id=UUID(org), case=obj, facts=[], documents=[],
            scan_status={}, open_issue_count=0,
            today=__import__("datetime").date(2027, 1, 1))
    assert "source_review_stale" in computed["blockers"]


def test_bad_format_even_when_reviewed_is_withheld(api, monkeypatch):
    client, _, factory = api
    org, case, url = make_case(api, "imm5476-review-invalid-format")
    doc_id = add_source_and_facts(api, org, case)
    monkeypatch.setattr(preview, "scan_status_by_document",
                        lambda *args: {doc_id: "cleared"})
    bad = {
        "identity.date_of_birth": "2001-02-30",
        "contact.email": "not-an-email",
        "representative.contact.email": "representative at example.test",
        "identity.uci": "invalid-identifier",
    }
    with factory() as db:
        for fact in db.query(CaseFact).filter(CaseFact.case_id == UUID(case)).all():
            if fact.field_path in bad:
                fact.value = bad[fact.field_path]
        db.commit()
    report = client.get(url).json()
    by_key = {f["key"]: f for f in report["fields"]}
    for key in ("applicant_dob", "applicant_email", "representative_email", "uci"):
        assert by_key[key]["status"] == "invalid_evidence_value"
        assert by_key[key]["value"] is None
        assert by_key[key]["evidence_ids"] == []
    assert report["verified_text_fields"] == 17
    assert report["verified_observed_subset"] is False
    assert "observed_fields_unresolved" in report["blockers"]
