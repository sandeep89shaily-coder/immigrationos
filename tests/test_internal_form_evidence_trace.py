"""Unified evidence-to-form trace: scoped status, provenance, and fail-closed rules."""
from types import SimpleNamespace as Obj
from uuid import UUID, uuid4

from app.internal_form_evidence_trace import build_trace
from app.models import CaseDocument, CaseFact, Membership
from tests.test_application_package import case_setup, start


def path(org, case):
    return f"/api/v1/orgs/{org}/cases/{case}/internal-form-evidence-trace"


def test_uninitialized_case_and_case_access_are_fail_closed(api):
    client, who, factory = api
    org, case, root = case_setup(api, "trace-uninitialized")
    assert client.get(path(org, case)).status_code == 409
    assert start(client, root, representative=False).status_code == 201
    response = client.get(path(org, case))
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["form_code"] == "IMM1294"
    assert data["counts"]["mapped_field_count"] == 14
    assert data["counts"]["unmapped_questionnaire_fields"] == 25
    assert data["counts"]["mapped_fields_with_reviewed_document_evidence"] == 0
    assert data["counts"]["unmapped_repeatable_history_fields"] == 0
    assert data["entire_ircc_form_complete"] is False
    assert data["official_pdf_fields_verified"] is False
    assert data["submission_supported"] is False
    assert all(r["official_pdf_field_id"] is None for r in data["rows"])
    assert all("value" not in r for r in data["rows"])
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="unassigned-trace",
                          role="consultant", is_active=True))
        db.commit()
    who["sub"] = "unassigned-trace"
    assert client.get(path(org, case)).status_code == 404
    who["sub"] = "unrelated-trace"
    assert client.get(path(org, case)).status_code == 404


def test_trace_scans_reconcile_source_conflict_and_evidence_changes(api, monkeypatch):
    from app import internal_form_evidence_trace as trace
    client, who, factory = api
    org, case, root = case_setup(api, "trace-case-evidence")
    assert start(client, root, representative=False).status_code == 201
    doc1, doc2 = uuid4(), uuid4()
    with factory() as db:
        for document in (doc1, doc2):
            db.add(CaseDocument(
                id=document, org_id=UUID(org), case_id=UUID(case),
                filename="fictional.pdf", document_type="passport",
                mime_type="application/pdf", size_bytes=120,
                sha256=str(document.hex) * 2, storage_key=uuid4().hex,
                uploaded_by_sub="fixture"))
        db.add(CaseFact(
            org_id=UUID(org), case_id=UUID(case), document_id=doc1,
            field_path="identity.given_name", value="Imaginary",
            review_status="verified", reviewed_by_sub="fixture",
            created_by_sub="fixture"))
        db.commit()
    first = client.get(path(org, case)).json()
    field = next(row for row in first["rows"]
                 if row["canonical_path"]=="identity.given_name")
    assert field["evidence_status"] == "source_scan_not_cleared"
    assert field["verified_evidence_ids"]==[]
    monkeypatch.setattr(trace, "scan_status_by_document",
                        lambda *args: {doc1: "cleared", doc2:"cleared"})
    second=client.get(path(org, case)).json()
    row=next(r for r in second["rows"] if r["canonical_path"]=="identity.given_name")
    assert row["review_status"]=="mapped_with_reviewed_document_evidence"
    assert row["case_document_ids"]==[str(doc1)]
    assert second["counts"]["mapped_fields_with_reviewed_document_evidence"]==1
    assert "Imaginary" not in str(second)
    assert second["snapshot_sha256"]!=first["snapshot_sha256"]
    with factory() as db:
        db.add(CaseFact(
            org_id=UUID(org), case_id=UUID(case), document_id=doc2,
            field_path="identity.given_name", value="Different",
            review_status="verified", reviewed_by_sub="fixture",
            created_by_sub="fixture"))
        db.commit()
    conflicted=client.get(path(org, case)).json()
    row=next(r for r in conflicted["rows"] if r["canonical_path"]=="identity.given_name")
    assert row["evidence_status"]=="conflicting_evidence"
    assert row["case_document_ids"]==[]
    assert conflicted["counts"]["mapped_fields_with_reviewed_document_evidence"]==0
    assert conflicted["snapshot_sha256"]!=second["snapshot_sha256"]


def test_trace_cannot_consume_other_case_facts_or_reuse_unscoped_history():
    case=Obj(org_id=uuid4(),id=uuid4(),client_id=uuid4())
    package=Obj(org_id=case.org_id,case_id=case.id,filing_context="outside_canada")
    source={"code":"IMM1294", "case_id":str(case.id),
            "manifest_sha256":"a"*64,"snapshot_sha256":"b"*64,
            "source_recheck_required":False,"blockers":[],
            "ircc_source_url":"https://www.canada.ca/ircc",
            "fields":[{"canonical_path":"identity.given_name",
                       "label":"Given name","status":"missing_evidence",
                       "condition_state":"active","source_url":None,
                       "source_section":None,"evidence_ids":[],
                       "document_ids":[],"source_hashes":[]}]}
    q={"path":"identity.given_name","label":"Given name","status":"missing_answer",
       "condition_state":"active","evidence_status":"missing_evidence",
       "latest_answer_decision":None,"has_latest_submitted_answer":False}
    worklist={"case_id":str(case.id),"questions":[q],
              "questionnaire_version":"v-test","latest_submission_id":None,
              "supplemental_disclosure_review":[]}
    unrelated=Obj(id=uuid4(),org_id=case.org_id,client_id=uuid4(),
                  kind="previous_relationship",version=1,details={})
    out=build_trace(case=case,package=package,coverage=source,
                    worklist=worklist,facts=[],supplemental_records=[unrelated])
    assert out["counts"]["unmapped_repeatable_history_fields"]==0
    assert out["official_pdf_fields_verified"] is False
    source["case_id"]=str(uuid4())
    try:
        build_trace(case=case,package=package,coverage=source,
                    worklist=worklist,facts=[],supplemental_records=[])
    except ValueError:
        pass
    else:
        assert False, "Cross-case coverage was accepted"
