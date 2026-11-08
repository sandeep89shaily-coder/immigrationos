"""Cross-form internal completeness must be case-scoped and fail closed."""
from uuid import UUID, uuid4

import pytest

from app import form_evidence_coverage as coverage
from app.models import CaseDocument, CaseFact, Membership
from tests.test_imm5476_case_preview import make_case


def endpoint(org, case, code="IMM1294", context="outside_canada"):
    return (f"/api/v1/orgs/{org}/ircc/cases/{case}/forms/{code}/"
            f"evidence-coverage?filing_context={context}")


def add_fact(api, org, case, path, value):
    _, _, factory = api
    doc = uuid4()
    with factory() as db:
        db.add(CaseDocument(
            id=doc, org_id=UUID(org), case_id=UUID(case),
            filename="synthetic-proof.pdf", document_type="passport",
            mime_type="application/pdf", size_bytes=100, sha256="c" * 64,
            storage_key=uuid4().hex, uploaded_by_sub="test-user-a"))
        db.add(CaseFact(
            org_id=UUID(org), case_id=UUID(case), document_id=doc,
            field_path=path, value=value, review_status="verified",
            created_by_sub="test-user-a", reviewed_by_sub="test-user-a"))
        db.commit()
    return doc


def test_empty_case_preview_reports_fourteen_gaps_and_never_exports(api):
    client, _, _ = api
    org, case, _ = make_case(api, "generic-evidence-missing")
    result = client.get(endpoint(org, case))
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    data = result.json()
    assert data["internal_preview_field_count"] == 24
    assert data["verified_preview_field_count"] == 0
    assert data["missing_preview_field_count"] == 18
    assert data["guided_source_field_count"] == 18
    assert data["entire_official_form_complete"] is False
    assert data["pdf_export_available"] is False
    assert data["submission_supported"] is False
    assert all(field["value"] is None for field in data["fields"])
    assert sum(row["status"] == "unresolved_condition" for row in data["fields"]) == 6


@pytest.mark.parametrize(("code", "context"), [
    ("IMM1294", "outside_canada"), ("IMM5709", "inside_canada"),
])
def test_reviewed_document_scan_and_source_change(code, context, api, monkeypatch):
    client, _, factory = api
    org, case, _ = make_case(api, "generic-evidence-" + code.lower())
    doc = add_fact(api, org, case, "identity.date_of_birth", "2001-06-09")
    url = endpoint(org, case, code, context)
    blocked = client.get(url).json()
    assert blocked["verified_preview_field_count"] == 0
    assert next(x for x in blocked["fields"] if x["canonical_path"] == "identity.date_of_birth")["status"] == "source_scan_not_cleared"
    monkeypatch.setattr(coverage, "scan_status_by_document", lambda *args: {doc: "cleared"})
    safe = client.get(url).json()
    assert safe["verified_preview_field_count"] == 1
    assert safe["snapshot_sha256"] != blocked["snapshot_sha256"]
    with factory() as db:
        fact = db.query(CaseFact).filter(CaseFact.case_id == UUID(case)).one()
        fact.value = "2001-02-30"
        db.commit()
    invalid = client.get(url).json()
    assert invalid["verified_preview_field_count"] == 0
    status = next(x for x in invalid["fields"] if x["canonical_path"] == "identity.date_of_birth")
    assert status["status"] == "invalid_evidence_value"
    assert status["value"] is None
    assert invalid["snapshot_sha256"] != safe["snapshot_sha256"]


def test_wrong_context_missing_registry_and_unassigned_member_denied(api):
    client, who, factory = api
    org, case, _ = make_case(api, "generic-evidence-access")
    assert client.get(endpoint(org, case, "IMM5709", "outside_canada")).status_code == 409
    assert client.get(endpoint(org, case, "IMM9999")).status_code == 404
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="unassigned-viewer",
                          role="viewer", is_active=True))
        db.commit()
    who["sub"] = "unassigned-viewer"
    assert client.get(endpoint(org, case)).status_code == 404
    who["sub"] = "outsider"
    assert client.get(endpoint(org, case)).status_code == 404


def test_contradictory_evidence_is_not_silently_selected(api, monkeypatch):
    client, _, factory = api
    org, case, _ = make_case(api, "generic-evidence-contradiction")
    first_doc = add_fact(api, org, case, "identity.family_name", "Sharma")
    second_doc = add_fact(api, org, case, "identity.family_name", "Kapoor")
    monkeypatch.setattr(coverage, "scan_status_by_document",
                        lambda *args: {first_doc: "cleared", second_doc: "cleared"})
    data = client.get(endpoint(org, case)).json()
    field = next(x for x in data["fields"] if x["canonical_path"] == "identity.family_name")
    assert field["status"] == "conflicting_evidence"
    assert field["value"] is None
    assert "unresolved_or_unsafe_evidence" in data["blockers"]


@pytest.mark.parametrize(("path", "value", "expected"), [
    ("identity.passport_issue_date", "2024-02-29", "verified_source_value"),
    ("identity.passport_expiry_date", "2024-02-30", "invalid_evidence_value"),
    ("education.program_start_date", "2027-01-15", "verified_source_value"),
    ("education.program_end_date", "not-a-date", "invalid_evidence_value"),
    ("finance.tuition_cad", "12000.00", "verified_source_value"),
    ("finance.available_funds_cad", "-1", "invalid_evidence_value"),
    ("finance.available_funds_cad", "NaN", "invalid_evidence_value"),
    ("finance.tuition_cad", "125.999", "invalid_evidence_value"),
    ("education.dli_number", "O123456789012", "verified_source_value"),
    ("education.dli_number", "bad space", "invalid_evidence_value"),
])
def test_source_guided_fields_never_promote_invalid_values(api, monkeypatch,
                                                           path, value, expected):
    client, _, _ = api
    org, case, _ = make_case(api, "guided-test-" + str(uuid4())[:9])
    doc = add_fact(api, org, case, path, value)
    monkeypatch.setattr(coverage, "scan_status_by_document",
                        lambda *args: {doc: "cleared"})
    data = client.get(endpoint(org, case)).json()
    field = next(x for x in data["fields"] if x["canonical_path"] == path)
    assert field["status"] == expected
    assert field["value"] == (value if expected == "verified_source_value" else None)
    assert field["source_url"].startswith("https://www.canada.ca/")
    assert field["source_section"]
    assert data["entire_official_form_complete"] is False
    assert data["pdf_export_available"] is False
    assert data["submission_supported"] is False


def test_source_guided_document_requires_scan_clearance(api, monkeypatch):
    client, _, _ = api
    org, case, _ = make_case(api, "guided-scan")
    doc = add_fact(api, org, case, "finance.tuition_cad", "10000.00")
    blocked = client.get(endpoint(org, case)).json()
    field = next(row for row in blocked["fields"]
                 if row["canonical_path"] == "finance.tuition_cad")
    assert field["status"] == "source_scan_not_cleared"
    assert field["value"] is None
    monkeypatch.setattr(coverage, "scan_status_by_document",
                        lambda *args: {doc: "cleared"})
    cleared = client.get(endpoint(org, case)).json()
    row = next(r for r in cleared["fields"]
               if r["canonical_path"] == "finance.tuition_cad")
    assert row["status"] == "verified_source_value"
    assert cleared["snapshot_sha256"] != blocked["snapshot_sha256"]


@pytest.mark.parametrize(("controller", "child"), [
    ("identity.has_other_names", "identity.other_family_name"),
    ("identity.has_national_id", "identity.national_id_number"),
])
def test_guidance_conditions_need_document_verified_parent_and_hide_inactive_evidence(
        api, monkeypatch, controller, child):
    client, _, factory = api
    org, case, _ = make_case(api, "conditional-coverage-" + str(uuid4())[:8])
    child_doc = add_fact(api, org, case, child, "SYNTHETIC")
    monkeypatch.setattr(coverage, "scan_status_by_document",
                        lambda *args: {child_doc: "cleared"})
    url = endpoint(org, case)
    unknown = client.get(url).json()
    row = next(x for x in unknown["fields"] if x["canonical_path"] == child)
    assert row["condition_state"] == "unresolved"
    assert row["value"] is None
    assert row["document_ids"] == []
    assert "conditional_applicability_unresolved" in unknown["blockers"]

    controller_doc = add_fact(api, org, case, controller, "no")
    # Even a reviewed but not scan-cleared controller cannot activate or
    # deactivate a branch. Only its documentary proof may do so.
    blocked = client.get(url).json()
    row = next(x for x in blocked["fields"] if x["canonical_path"] == child)
    assert row["condition_state"] == "unresolved"
    monkeypatch.setattr(coverage, "scan_status_by_document",
                        lambda *args: {child_doc: "cleared",
                                       controller_doc: "cleared"})
    inactive = client.get(url).json()
    row = next(x for x in inactive["fields"] if x["canonical_path"] == child)
    assert row["condition_state"] == "inactive"
    assert row["status"] == "inactive_condition"
    assert row["value"] is None
    assert row["evidence_ids"] == []

    with factory() as db:
        fact = db.query(CaseFact).filter(
            CaseFact.case_id == UUID(case),
            CaseFact.field_path == controller).one()
        fact.value = "yes"
        db.commit()
    active = client.get(url).json()
    row = next(x for x in active["fields"] if x["canonical_path"] == child)
    assert row["condition_state"] == "active"
    assert row["status"] == "verified_source_value"
    assert row["value"] == "SYNTHETIC"
    assert active["snapshot_sha256"] != inactive["snapshot_sha256"]


def test_unsure_declaration_and_invalid_national_id_date_never_verify(api, monkeypatch):
    client, _, _ = api
    org, case, _ = make_case(api, "guidance-uncertain-date")
    flag_doc = add_fact(api, org, case, "identity.has_national_id", "unsure")
    date_doc = add_fact(api, org, case, "identity.national_id_issue_date", "2025-02-30")
    monkeypatch.setattr(coverage, "scan_status_by_document",
                        lambda *args: {flag_doc: "cleared", date_doc: "cleared"})
    data = client.get(endpoint(org, case)).json()
    flag = next(x for x in data["fields"]
                if x["canonical_path"] == "identity.has_national_id")
    date_field = next(x for x in data["fields"]
                      if x["canonical_path"] == "identity.national_id_issue_date")
    assert flag["status"] == "invalid_evidence_value"
    assert date_field["status"] == "unresolved_condition"
    assert date_field["value"] is None
    assert data["entire_official_form_complete"] is False
