"""Fail-closed form preparation tests with synthetic study-permit cases."""
from uuid import UUID

from app.form_preparation import _render_snapshot
from app.form_preparation_models import FormPreparationPacket
from app.models import Membership
from tests.test_application_package import case_setup, start


def setup(api, slug="form-prep-demo"):
    client, _, _ = api
    org, case, pkg = case_setup(api, slug)
    assert start(client, pkg, representative=False).status_code == 201
    return org, case, f"/api/v1/orgs/{org}/cases/{case}/form-preparation"


def test_preview_blocks_unverified_profile_data_and_no_official_form(api):
    client, who, factory = api
    org, case, root = setup(api, "form-prep-blockers")
    response = client.get(root + "/preview")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["form_code"] == "IMM1294"
    assert data["verified_subset_complete"] is False
    assert data["official_pdf_autofill_supported"] is False
    assert data["all_official_form_fields_mapped"] is False
    assert len(data["fields"]) >= 5
    assert "required_preview_fields_unresolved" in data["blockers"]
    assert client.post(root + "/packets", json={
        "expected_sha256": data["snapshot_sha256"],
        "acknowledge_internal_subset_only": True}).status_code == 409
    assert client.post(root + "/packets", json={
        "expected_sha256": data["snapshot_sha256"],
        "acknowledge_internal_subset_only": False}).status_code == 422
    assert client.post(root + "/packets", json={
        "expected_sha256": "0" * 64,
        "acknowledge_internal_subset_only": True}).status_code == 409
    assert client.get(root + "/packets").json() == []
    with factory() as db:
        assert db.query(FormPreparationPacket).count() == 0


def test_inside_study_permit_has_correct_internal_preview_context(api):
    client, _, _ = api
    org, case, pkg = case_setup(api, "form-prep-inside")
    assert start(client, pkg, context="inside_canada", representative=False).status_code == 201
    root = f"/api/v1/orgs/{org}/cases/{case}/form-preparation"
    data = client.get(root + "/preview").json()
    assert data["form_code"] == "IMM5709"
    assert data["mapping_version"] == "canonical-study-reviewed-manifest-v2"
    assert data["submission_supported"] is False


def test_other_firm_and_unassigned_consultant_denied(api):
    client, who, factory = api
    org, case, root = setup(api, "form-prep-access")
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="unassigned-consultant",
                          role="consultant", is_active=True))
        db.commit()
    who["sub"] = "unassigned-consultant"
    assert client.get(root + "/preview").status_code == 404
    assert client.get(root + "/packets").status_code == 404
    assert client.post(root + "/packets", json={
        "expected_sha256": "0" * 64,
        "acknowledge_internal_subset_only": True}).status_code == 404
    who["sub"] = "outsider"
    assert client.get(root + "/preview").status_code == 404


def test_source_without_cleared_scan_does_not_create_preparation_packet(api):
    client, who, factory = api
    org, case, root = setup(api, "form-prep-scan")
    from app.models import CaseDocument, CaseFact
    from uuid import uuid4
    from app.ircc_registry import REGISTRY
    with factory() as db:
        document = CaseDocument(id=uuid4(), org_id=UUID(org), case_id=UUID(case),
            filename="fictional-passport.pdf", document_type="passport",
            mime_type="application/pdf", size_bytes=20, sha256="f" * 64,
            storage_key=uuid4().hex, uploaded_by_sub="test-user-a")
        db.add(document)
        db.flush()
        for _, path in REGISTRY["IMM1294"].preview_fields:
            db.add(CaseFact(org_id=UUID(org), case_id=UUID(case), document_id=document.id,
                            field_path=path, value="Fictional", review_status="verified",
                            created_by_sub="test-user-a", reviewed_by_sub="test-user-a"))
        db.commit()
    preview = client.get(root + "/preview")
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["verified_subset_complete"] is False
    assert all(row["status"] == "source_scan_not_cleared" for row in data["fields"])
