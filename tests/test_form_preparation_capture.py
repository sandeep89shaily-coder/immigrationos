"""Positive path for immutable internal form packets using fictional cleared sources."""
from uuid import UUID, uuid4

from app import form_preparation as prep
from app.models import CaseDocument, CaseFact
from app.form_preparation_models import FormPreparationPacket
from app.ircc_registry import REGISTRY
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
        for _, field_path in REGISTRY["IMM1294"].preview_fields:
            db.add(CaseFact(org_id=UUID(org), case_id=UUID(case),
                            document_id=doc_id, field_path=field_path,
                            value="Synthetic value", review_status="verified",
                            created_by_sub="test-user-a", reviewed_by_sub="test-user-a"))
        db.commit()
    # This test explicitly injects an external scan result; production code
    # obtains status only from recorded portal submissions.
    monkeypatch.setattr(prep, "_scan_map", lambda db, org_id, case_id: {doc_id: "cleared"})
    snapshot = client.get(root + "/preview")
    assert snapshot.status_code == 200, snapshot.text
    data = snapshot.json()
    assert data["verified_subset_complete"] is True
    assert data["official_pdf_autofill_supported"] is False
    created = client.post(root + "/packets", json={
        "expected_sha256": data["snapshot_sha256"],
        "acknowledge_internal_subset_only": True})
    assert created.status_code == 201, created.text
    assert created.json()["fields"] == data["fields"]
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
