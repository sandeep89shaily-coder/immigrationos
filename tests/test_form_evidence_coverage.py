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


def test_empty_case_preview_reports_six_gaps_and_never_exports(api):
    client, _, _ = api
    org, case, _ = make_case(api, "generic-evidence-missing")
    result = client.get(endpoint(org, case))
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    data = result.json()
    assert data["internal_preview_field_count"] == 6
    assert data["verified_preview_field_count"] == 0
    assert data["missing_preview_field_count"] == 6
    assert data["entire_official_form_complete"] is False
    assert data["pdf_export_available"] is False
    assert data["submission_supported"] is False
    assert all(field["value"] is None for field in data["fields"])


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
