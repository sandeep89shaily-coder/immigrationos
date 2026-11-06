"""One real case worklist: filing route, IRCC forms, evidence and reviewed copies.

Tests use fictional forms only; not a verified government PDF adapter.
"""
from hashlib import sha256
from uuid import UUID, uuid4
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app import application_package as pkgapi
from app.malware_scan import ScanVerdict, ScannerUnavailable
from app.models import CaseDocument, Membership
from app.package_models import CaseApplicationPackage, PackageFormCopy
from tests.test_api import new_org, new_client


PDF = b"%PDF-1.4\nSynthetic fictional unsigned PDF for test suite\n%%EOF\n"


def case_setup(api, slug="package-core", application_type="study_permit"):
    client, _, _ = api
    org = new_org(client, slug)
    person = new_client(client, org)
    res = client.post(f"/api/v1/orgs/{org}/cases", json={
        "client_id": person, "application_type": application_type,
        "title": "Fictional case package"})
    assert res.status_code == 201, res.text
    return org, res.json()["id"], f"/api/v1/orgs/{org}/cases/{res.json()['id']}/package"


def start(client, url, context="outside_canada", representative=True):
    return client.post(url, json={
        "filing_context": context,
        "include_representative_form": representative,
    })


def add_pdf(api, org, case, *, filename="fictional-form.pdf", mime="application/pdf", blob=PDF):
    _, _, factory = api
    doc = CaseDocument(
        id=uuid4(), org_id=UUID(org), case_id=UUID(case),
        filename=filename, document_type="ircc_form", mime_type=mime,
        size_bytes=len(blob), sha256=sha256(blob).hexdigest(),
        storage_key=uuid4().hex, uploaded_by_sub="test-user-a")
    with factory() as db:
        db.add(doc)
        db.commit()
    return str(doc.id)


def monkey_scan(monkeypatch, status="cleared"):
    monkeypatch.setattr(pkgapi, "load_blob", lambda key: PDF)
    if status == "offline":
        def bad(data):
            raise ScannerUnavailable("test scanner offline")
        monkeypatch.setattr(pkgapi, "scan_bytes", bad)
    else:
        monkeypatch.setattr(pkgapi, "scan_bytes",
                            lambda data: ScanVerdict(status=status))


def link(client, url, code, document_id):
    return client.post(url+f"/forms/{code}/copies", json={"document_id": document_id})


def review(client, url, copy_id, decision="accept", checked=True):
    return client.post(url + f"/copies/{copy_id}/review", json={
        "decision": decision,
        "note": "Fictional PDF compared against current official instructions and client evidence.",
        "current_ircc_source_checked": checked,
        "reviewed_pdf_in_appropriate_software": True,
    })


def test_study_permit_context_pins_form_and_reuses_existing_evidence_matrix(api):
    client, _, _ = api
    org, case, root = case_setup(api, "package-context")
    unstarted = client.get(root)
    assert unstarted.status_code == 200
    assert unstarted.json()["initialized"] is False
    assert unstarted.json()["submission_supported"] is False

    outside = start(client, root, "outside_canada", True)
    assert outside.status_code == 201, outside.text
    data = outside.json()
    assert [f["code"] for f in data["forms"]] == ["IMM1294", "IMM5476"]
    assert len(data["document_requirements"]) >= 4
    assert any(r["key"] == "passport" for r in data["document_requirements"])
    assert data["official_pdf_autofill_supported"] is False
    assert data["official_validation_verified"] is False
    assert data["submission_supported"] is False
    assert data["release_status"] == "blocked_official_validation_not_implemented"
    assert data["all_selected_form_copies_staff_reviewed"] is False
    assert start(client, root, "outside_canada", True).status_code == 201
    assert start(client, root, "inside_canada", True).status_code == 409
    assert start(client, root, "outside_canada", False).status_code == 409


def test_inside_canada_form_selection_and_nonstudy_block(api):
    client, _, _ = api
    _, _, url = case_setup(api, "package-inside")
    r = start(client, url, "inside_canada", False)
    assert r.status_code == 201, r.text
    assert [x["code"] for x in r.json()["forms"]] == ["IMM5709"]
    assert r.json()["include_representative_form"] is False
    assert start(client, url, "wrong", False).status_code == 422
    _, _, nonstudy = case_setup(api, "package-visitor", "visitor")
    assert client.get(nonstudy).status_code == 409
    assert start(client, nonstudy).status_code == 409


def test_pdf_copy_requires_real_scan_and_human_review(api, monkeypatch):
    client, _, factory = api
    org, case, root = case_setup(api, "package-copy")
    assert start(client, root).status_code == 201
    document_id = add_pdf(api, org, case)
    monkey_scan(monkeypatch)
    r = link(client, root, "IMM1294", document_id)
    assert r.status_code == 201, r.text
    copy_id = r.json()["copy_id"]
    assert r.json()["official_validation_verified"] is False
    summary = client.get(root).json()
    assert summary["forms"][0]["status"] == "pending_professional_review"
    assert summary["forms"][0]["latest_copy"]["document_id"] == document_id
    assert review(client, root, copy_id, checked=False).status_code == 422
    accepted = review(client, root, copy_id)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["review_status"] == "accepted"
    assert accepted.json()["submission_supported"] is False
    assert review(client, root, copy_id).status_code == 409
    summary = client.get(root).json()
    assert summary["forms"][0]["status"] == "staff_reviewed_copy"
    assert summary["all_selected_form_copies_staff_reviewed"] is False  # IMM5476 still missing.
    assert summary["official_validation_verified"] is False
    with factory() as db:
        x = db.query(PackageFormCopy).one()
        assert x.reviewed_by_sub == "test-user-a"
        assert x.linked_document_sha256 == sha256(PDF).hexdigest()
        assert x.source_revision == summary["forms"][0]["source_revision"]


def test_quarantine_and_rescan_are_fail_closed(api, monkeypatch):
    client, _, _ = api
    org, case, root = case_setup(api, "package-quarantine")
    assert start(client, root, representative=False).status_code == 201
    doc = add_pdf(api, org, case)
    monkey_scan(monkeypatch, "offline")
    r = link(client, root, "IMM1294", doc)
    assert r.status_code == 201 and r.json()["scan_status"] == "quarantined"
    copy_id = r.json()["copy_id"]
    assert client.get(root).json()["forms"][0]["status"] == "quarantined"
    assert review(client, root, copy_id).status_code == 423
    assert client.post(root+f"/copies/{copy_id}/scan").status_code == 503
    monkey_scan(monkeypatch, "cleared")
    assert client.post(root+f"/copies/{copy_id}/scan").json()["scan_status"] == "cleared"
    assert review(client, root, copy_id).status_code == 200
    assert client.get(root).json()["all_selected_form_copies_staff_reviewed"] is True
    assert client.get(root).json()["submission_supported"] is False


def test_upload_replacement_never_overwrites_old_review(api, monkeypatch):
    client, _, factory = api
    org, case, root = case_setup(api, "package-versions")
    start(client, root, representative=False)
    monkey_scan(monkeypatch)
    first = add_pdf(api, org, case)
    a = link(client, root, "IMM1294", first)
    assert a.status_code == 201
    assert review(client, root, a.json()["copy_id"]).status_code == 200
    second = add_pdf(api, org, case)
    b = link(client, root, "IMM1294", second)
    assert b.status_code == 201
    assert b.json()["copy_id"] != a.json()["copy_id"]
    assert client.get(root).json()["forms"][0]["status"] == "pending_professional_review"
    assert client.get(root).json()["forms"][0]["copy_count"] == 2
    assert review(client, root, a.json()["copy_id"]).status_code == 409
    assert review(client, root, b.json()["copy_id"], "reject").status_code == 200
    assert client.get(root).json()["forms"][0]["status"] == "rejected_by_reviewer"
    with factory() as db:
        statuses = sorted(x.review_status for x in db.query(PackageFormCopy).all())
        assert statuses == ["accepted", "rejected"]


def test_same_case_document_fk_and_role_isolation(api, monkeypatch):
    client, who, factory = api
    org, case, root = case_setup(api, "package-fk")
    start(client, root, representative=False)
    other = client.post(f"/api/v1/orgs/{org}/cases", json={
        "client_id": new_client(client, org),
        "application_type": "study_permit", "title": "Other fictional case",
    }).json()["id"]
    foreign_doc = add_pdf(api, org, other)
    monkey_scan(monkeypatch)
    assert link(client, root, "IMM1294", foreign_doc).status_code == 404
    good = add_pdf(api, org, case)
    assert link(client, root, "IMM5476", good).status_code == 409
    assert link(client, root, "IMM1294", good).status_code == 201
    assert link(client, root, "IMM1294", good).status_code == 409
    with factory() as db:
        record = db.query(CaseApplicationPackage).one()
        db.add(PackageFormCopy(
            org_id=UUID(org), case_id=UUID(case), package_id=record.id,
            document_id=UUID(foreign_doc), form_code="IMM1294",
            source_revision="fictional", source_observed_on=date(2026,11,6),
            linked_document_sha256=sha256(PDF).hexdigest(), scan_status="quarantined",
            review_status="pending", created_by_sub="test-user-a"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(Membership(org_id=UUID(org), subject="unassigned-reviewer",
                          role="consultant", is_active=True))
        db.commit()
    who["sub"] = "unassigned-reviewer"
    assert client.get(root).status_code == 404
    assert start(client, root).status_code == 404
    who["sub"] = "outsider"
    assert client.get(root).status_code == 404


def test_non_pdf_and_scan_rejection_cannot_be_reviewed(api, monkeypatch):
    client, _, _ = api
    org, case, root = case_setup(api, "package-pdf-type")
    start(client, root, representative=False)
    txt = add_pdf(api, org, case, filename="fake.txt", mime="text/plain")
    assert link(client, root, "IMM1294", txt).status_code == 415
    malicious = add_pdf(api, org, case)
    monkey_scan(monkeypatch, "rejected")
    r = link(client, root, "IMM1294", malicious)
    assert r.status_code == 201 and r.json()["scan_status"] == "rejected"
    assert review(client, root, r.json()["copy_id"]).status_code == 423
    assert client.get(root).json()["forms"][0]["status"] == "scanner_rejected"
