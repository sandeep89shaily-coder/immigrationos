"""Threat-focused tests for the incomplete, human-reviewed IRCC preflight."""
from dataclasses import replace
import pytest
from datetime import date
from uuid import UUID, uuid4

from app.ircc_registry import REGISTRY
from app.models import AuditEvent, CaseDocument, CaseFact, CaseIssue, Membership
from app.portal_models import DocumentRequest, PortalSubmission
from tests.test_ircc_registry import setup_case


@pytest.fixture(autouse=True)
def fixed_review_date(monkeypatch):
    """Keep fixture results independent of calendar age; stale-source test changes source."""
    import app.form_preflight as preflight
    original = preflight.source_metadata
    monkeypatch.setattr(preflight, "source_metadata", lambda source, today=None:
                        original(source, today=today or date(2026, 11, 6)))


def _url(org, case):
    return f"/api/v1/orgs/{org}/ircc/cases/{case}/forms/IMM1294/preflight?filing_context=outside_canada"


def _verified_fields(api, org, case):
    _, _, factory = api
    with factory() as db:
        doc = CaseDocument(
            org_id=UUID(org), case_id=UUID(case), filename="synthetic.txt",
            document_type="fictional_letter", mime_type="text/plain",
            size_bytes=20, sha256="a" * 64, storage_key=f"test-{uuid4()}",
            uploaded_by_sub="synthetic-staff")
        db.add(doc)
        db.flush()
        fields = [
            ("identity.given_name", "Avery"),
            ("identity.family_name", "Example"),
            ("identity.date_of_birth", "2001-01-02"),
            ("identity.citizenship", "Fictionland"),
            ("identity.passport_number", "FICTIONAL1234"),
            ("education.institution", "Sample College"),
        ]
        for path, value in fields:
            db.add(CaseFact(
                org_id=UUID(org), case_id=UUID(case), document_id=doc.id,
                field_path=path, value=value, review_status="verified",
                created_by_sub="synthetic-staff", reviewed_by_sub="synthetic-reviewer"))
        db.commit()
        return doc.id


def test_internal_review_acknowledgement_bound_to_exact_evidence_snapshot(api):
    client, who, factory = api
    org, case = setup_case(api, "preflight-ack")
    document_id = _verified_fields(api, org, case)
    url = _url(org, case)
    initial = client.get(url)
    assert initial.status_code == 200, initial.text
    payload = initial.json()
    assert payload["internal_preflight_status"] == "reviewable"
    assert payload["release_status"] == "blocked_no_validated_ircc_pdf_adapter"
    assert payload["submission_supported"] is False
    assert payload["acknowledgement"] == "not_acknowledged"
    assert all(f["status"] == "verified" for f in payload["fields"])
    assert all(f["document_ids"] == [str(document_id)] for f in payload["fields"])
    assert client.post(url.replace("?filing_context", "/acknowledge?filing_context"),
                       json={"snapshot_sha256": "0" * 64}).status_code == 409
    ack = client.post(url.replace("?filing_context", "/acknowledge?filing_context"),
                      json={"snapshot_sha256": payload["snapshot_sha256"]})
    assert ack.status_code == 200, ack.text
    assert ack.json()["acknowledgement"] == "current"
    assert client.get(url).json()["acknowledgement"] == "current"
    with factory() as db:
        audit = db.query(AuditEvent).filter(
            AuditEvent.org_id == UUID(org),
            AuditEvent.action == "form.internal_preflight_acknowledged").all()
        assert len(audit) == 1
        assert audit[0].details["snapshot_sha256"] == payload["snapshot_sha256"]
        assert "FICTIONAL1234" not in str(audit[0].details)
    # Adding even one UNMAPPED pending claim invalidates the acknowledgement.
    changed = client.post(f"/api/v1/orgs/{org}/cases/{case}/facts",
                          json={"field_path": "history.optional_note", "value": "Synthetic"})
    assert changed.status_code == 201, changed.text
    after = client.get(url).json()
    assert after["snapshot_sha256"] != payload["snapshot_sha256"]
    assert after["acknowledgement"] == "stale"
    assert after["internal_preflight_status"] == "blocked"
    assert client.post(url.replace("?filing_context", "/acknowledge?filing_context"),
                       json={"snapshot_sha256": payload["snapshot_sha256"]}).status_code == 409


def test_only_reviewer_roles_can_acknowledge_and_tenant_isolation(api):
    client, who, factory = api
    org, case = setup_case(api, "preflight-roles")
    _verified_fields(api, org, case)
    url = _url(org, case)
    digest = client.get(url).json()["snapshot_sha256"]
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="assistant-user",
                          role="assistant", is_active=True))
        db.commit()
    who["sub"] = "assistant-user"
    assert client.get(url).status_code == 404  # No active case-specific grant.
    ack_url = url.replace("?filing_context", "/acknowledge?filing_context")
    assert client.post(ack_url, json={"snapshot_sha256": digest}).status_code == 404
    who["sub"] = "unrelated-person"
    assert client.get(url).status_code == 404
    assert client.post(ack_url, json={"snapshot_sha256": digest}).status_code == 404
    who["sub"] = "test-user-a"
    assert client.get(url.replace("outside_canada", "inside_canada")).status_code == 409
    assert client.get(url.replace("IMM1294", "IMM9999")).status_code == 404


def test_quarantined_document_cannot_supply_verified_form_fields(api):
    client, who, factory = api
    org, case = setup_case(api, "preflight-quarantine")
    doc_id = _verified_fields(api, org, case)
    with factory() as db:
        request = DocumentRequest(
            org_id=UUID(org), case_id=UUID(case), title="Synthetic document",
            instructions="", document_type="test", created_by_sub="synthetic-staff")
        db.add(request)
        db.flush()
        db.add(PortalSubmission(
            org_id=UUID(org), case_id=UUID(case), request_id=request.id,
            document_id=doc_id, uploaded_by_sub="synthetic-client",
            scan_status="quarantined"))
        db.commit()
    data = client.get(_url(org, case)).json()
    assert data["internal_preflight_status"] == "blocked"
    assert any("quarantined" in s for s in data["blockers"])
    assert all(f["value"] is None for f in data["fields"])
    legacy_preview = client.get(
        f"/api/v1/orgs/{org}/ircc/cases/{case}/forms/IMM1294/preview"
        "?filing_context=outside_canada").json()
    assert legacy_preview["excluded_untrusted_document_facts"] == 6
    assert all(f["value"] is None for f in legacy_preview["fields"])
    assert client.post(_url(org, case).replace("?filing_context", "/acknowledge?filing_context"),
                       json={"snapshot_sha256": data["snapshot_sha256"]}).status_code == 409


def test_open_issues_and_stale_official_source_block_acknowledgement(api, monkeypatch):
    client, _, factory = api
    org, case = setup_case(api, "preflight-stale")
    _verified_fields(api, org, case)
    with factory() as db:
        db.add(CaseIssue(
            org_id=UUID(org), case_id=UUID(case), fingerprint="f" * 64,
            field_path="identity.given_name", issue_type="conflicting_evidence",
            description="Synthetic discrepancy", severity="review", status="open"))
        db.commit()
    first = client.get(_url(org, case)).json()
    assert any("Unresolved evidence" in s for s in first["blockers"])
    old = REGISTRY["IMM1294"]
    monkeypatch.setitem(REGISTRY, "IMM1294", replace(old, last_checked=date(2020, 1, 1)))
    stale = client.get(_url(org, case)).json()
    assert stale["source_recheck_required"] is True
    assert any("older than 30 days" in s for s in stale["blockers"])


def test_verified_mapped_fact_without_document_provenance_blocks_review(api):
    client, _, factory = api
    org, case = setup_case(api, "preflight-provenance")
    _verified_fields(api, org, case)
    with factory() as db:
        db.add(CaseFact(
            org_id=UUID(org), case_id=UUID(case), document_id=None,
            field_path="identity.given_name", value="Avery",
            review_status="verified", created_by_sub="synthetic-staff",
            reviewed_by_sub="synthetic-reviewer"))
        db.commit()
    result = client.get(_url(org, case))
    assert result.status_code == 200, result.text
    assert result.json()["internal_preflight_status"] == "blocked"
    assert any("lacks a linked supporting document" in s for s in result.json()["blockers"])
