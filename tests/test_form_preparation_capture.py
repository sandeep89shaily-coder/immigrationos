"""Positive path for immutable internal form packets using fictional cleared sources."""
from uuid import UUID, uuid4

from app import form_preparation as prep
from app.models import CaseDocument, CaseFact
from app.form_preparation_models import FormPreparationPacket
from app.ircc_registry import REGISTRY
from app.form_manifest import MANIFESTS
from tests.test_form_preparation import setup


def test_preparation_snapshot_captures_verified_subset_only(api, monkeypatch):
    client, who, factory = api
    org, case, root = setup(api, "form-prep-positive")
    doc_id = uuid4()
    with factory() as db:
        db.add(CaseDocument(id=doc_id, org_id=UUID(org), case_id=UUID(case),
                            filename="fictional-reviewed-source.pdf", document_type="passport",
                            mime_type="application/pdf", size_bytes=100,
                            sha256="d" * 64, storage_key=uuid4().hex,
                            uploaded_by_sub="test-user-a"))
        values = {
            "identity.date_of_birth": "2002-04-21",
            "identity.passport_issue_date": "2021-01-01",
            "identity.passport_expiry_date": "2031-01-01",
            "education.program_start_date": "2027-09-01",
            "education.program_end_date": "2029-06-01",
            "finance.tuition_cad": "15000.00",
            "finance.available_funds_cad": "30000.00",
            "education.dli_number": "O123456789012",
            "identity.has_other_names": "no",
            "identity.has_national_id": "no",
            "history.has_previous_relationships": "no",
            "history.has_foreign_residences": "no",
        }
        dependent = {
            "identity.other_family_name", "identity.other_given_name",
            "identity.national_id_number", "identity.national_id_country",
            "identity.national_id_issue_date", "identity.national_id_expiry_date",
        }
        all_paths = {field.canonical_path
                     for section in MANIFESTS["IMM1294"].sections
                     for field in section.fields}
        assert len(all_paths) == 24
        for field_path in sorted(all_paths - dependent):
            db.add(CaseFact(org_id=UUID(org), case_id=UUID(case),
                            document_id=doc_id, field_path=field_path,
                            value=values.get(field_path, "Synthetic"),
                            review_status="verified",
                            created_by_sub="test-user-a", reviewed_by_sub="test-user-a"))
        db.commit()
    # This test explicitly injects an external scan result; production code
    # obtains status only from recorded portal submissions.
    monkeypatch.setattr(prep, "_scan_map", lambda db, org_id, case_id: {doc_id: "cleared"})
    snapshot = client.get(root + "/preview")
    assert snapshot.status_code == 200, snapshot.text
    data = snapshot.json()
    assert data["verified_subset_complete"] is True
    assert data["manifest_field_count"] == 24
    assert data["manifest_verified_field_count"] == 18
    assert len(data["manifest_sha256"]) == 64
    assert len(data["manifest_coverage_sha256"]) == 64
    assert data["official_pdf_autofill_supported"] is False
    created = client.post(root + "/packets", json={
        "expected_sha256": data["snapshot_sha256"],
        "acknowledge_internal_subset_only": True})
    assert created.status_code == 201, created.text
    assert created.json()["fields"] == data["fields"]
    assert created.json()["manifest_sha256"] == data["manifest_sha256"]
    assert created.json()["manifest_verified_field_count"] == 18
    assert created.json()["submission_supported"] is False
    with factory() as db:
        fact = db.query(CaseFact).filter(CaseFact.org_id == UUID(org),
                                       CaseFact.case_id == UUID(case)).first()
        fact.value = "Changed synthetic value"
        db.commit()
    new = client.get(root + "/preview").json()
    assert new["snapshot_sha256"] != data["snapshot_sha256"]
    assert client.post(root + "/packets", json={
        "expected_sha256": data["snapshot_sha256"],
        "acknowledge_internal_subset_only": True}).status_code == 409
    persisted = client.get(root + "/packets").json()
    assert len(persisted) == 1
    assert persisted[0]["snapshot_sha256"] == data["snapshot_sha256"]
    with factory() as db:
        assert db.query(FormPreparationPacket).count() == 1


def test_legacy_six_field_packet_cannot_bypass_current_manifest_gate(api, monkeypatch):
    client, who, factory = api
    org, case, root = setup(api, "form-prep-six-only-not-enough")
    doc_id = uuid4()
    with factory() as db:
        db.add(CaseDocument(id=doc_id, org_id=UUID(org), case_id=UUID(case),
                            filename="synthetic.pdf", document_type="passport",
                            mime_type="application/pdf", size_bytes=100, sha256="e"*64,
                            storage_key=uuid4().hex, uploaded_by_sub="test-user-a"))
        for _, key in REGISTRY["IMM1294"].preview_fields:
            value = "2002-04-21" if key == "identity.date_of_birth" else "Synthetic"
            db.add(CaseFact(org_id=UUID(org), case_id=UUID(case),
                            document_id=doc_id, field_path=key,
                            value=value, review_status="verified",
                            created_by_sub="test-user-a", reviewed_by_sub="test-user-a"))
        db.commit()
    monkeypatch.setattr(prep, "_scan_map", lambda db, org_id, case_id: {doc_id:"cleared"})
    preview=client.get(root+"/preview")
    assert preview.status_code==200, preview.text
    data=preview.json()
    assert all(x["status"]=="verified_subset_field" for x in data["fields"])
    assert data["manifest_field_count"]==24
    assert data["manifest_verified_field_count"]==6
    assert "current_internal_manifest_unresolved" in data["blockers"]
    assert data["verified_subset_complete"] is False
    attempt=client.post(root+"/packets",json={
        "expected_sha256":data["snapshot_sha256"],
        "acknowledge_internal_subset_only":True})
    assert attempt.status_code==409, attempt.text
    assert client.get(root+"/packets").json()==[]
