"""Synthetic end-to-end CICC s24 service engagement and case assignment tests."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app import engagement
from app.engagement_models import (EngagementScreen, ServiceAgreementDraft,
                                   ServiceSignedCopy, MatterAssignment)
from app.malware_scan import ScanVerdict, ScannerUnavailable
from app.models import AuditEvent, Case, Membership
from tests.test_api import new_org, new_client


def setup(api, slug):
    client, who, _ = api
    org = new_org(client, slug)
    user = new_client(client, org)
    return org, user, f"/api/v1/orgs/{org}/engagements/clients/{user}"


def screening(client, url, *, prior="none", conflict="none_identified", note=None):
    result = client.post(url + "/screens", json={
        "client_identity_verified": True,
        "previous_rep_checked": True,
        "prior_rep": prior, "conflict_status": conflict,
        "details": note or "Fictional client identity and prior representation reviewed independently.",
        "independently_reviewed_conflicts": True,
    })
    assert result.status_code == 201, result.text
    return result.json()


def draft(client, url):
    clauses = {key: f"Synthetic reviewed content for {label}, no legal advice is provided."
               for key, label in engagement.CLAUSES.items()}
    result = client.post(url + "/drafts", json={
        "clauses": clauses, "professional_checked_current_code": True
    })
    assert result.status_code == 201, result.text
    return result.json(), clauses


def mock_pdf(monkeypatch, scan="cleared"):
    data = b"%PDF-1.4\nDummy signed service agreement, fictional only\n%%EOF\n"
    monkeypatch.setattr(engagement, "save_blob",
                        lambda raw, mime: ("0"*32, sha256(raw).hexdigest()))
    monkeypatch.setattr(engagement, "load_blob", lambda key: data)
    monkeypatch.setattr(engagement, "delete_failed_blob", lambda key: None)
    if scan == "offline":
        def fail(raw):
            raise ScannerUnavailable("offline")
        monkeypatch.setattr(engagement, "scan_bytes", fail)
    else:
        monkeypatch.setattr(engagement, "scan_bytes",
                            lambda raw: ScanVerdict(status=scan))
    return data


def upload(client, url, draft_id, content):
    base = datetime.now(timezone.utc) + timedelta(seconds=1)
    return client.post(url + f"/drafts/{draft_id}/signed-copy", data={
        "draft_provided_at": base.isoformat(),
        "signed_at": (base + timedelta(seconds=1)).isoformat(),
        "client_copy_provided_at": (base + timedelta(seconds=2)).isoformat(),
    }, files={"file": ("synthetic-signed.pdf", content, "application/pdf")})


def review(client, url, draft_id, decision="accept"):
    return client.post(url + f"/drafts/{draft_id}/review", json={
        "decision": decision, "reviewer_confirmed_signed_terms_and_delivery": True,
        "note": "Fictional signed copy, delivery time and current terms personally reviewed.",
    })


def open_matter(client, url, professional="test-user-a"):
    return client.post(url + "/open-matter", json={
        "application_type": "work_permit",
        "title": "Synthetic work permit client matter",
        "professional_sub": professional,
        "confirm_engagement_and_professional_assignment": True,
    })


def test_conflict_and_prior_rep_hold_prevent_agreement_or_case(api):
    client, _, _ = api
    org, c, url = setup(api, "engagement-hold")
    assert open_matter(client, url).status_code == 409
    screening(client, url, prior="concurrent")
    r = client.post(url + "/drafts", json={
        "clauses": {key:"reviewed clause" for key in engagement.CLAUSES},
        "professional_checked_current_code": True,
    })
    assert r.status_code == 409
    assert client.get(url).json()["screen"]["clear_for_drafting"] is False
    screening(client, url, prior="none", conflict="potential")
    assert client.get(url).json()["screen"]["clear_for_drafting"] is False
    assert open_matter(client, url).status_code == 409
    screening(client, url, prior="ended_in_writing", conflict="none_identified")
    assert client.get(url).json()["screen"]["clear_for_drafting"] is True


def test_s24_requires_all_26_professionally_reviewed_sections(api):
    client, _, _ = api
    _, _, url = setup(api, "engagement-clauses")
    screening(client, url)
    assert len(engagement.CLAUSES) == 26
    code = client.post(url + "/drafts", json={
        "clauses": {"a_licensee": "Synthetic"}, "professional_checked_current_code": True})
    assert code.status_code == 422
    draft_data, fields = draft(client, url)
    assert draft_data["clauses_covered"] == 26
    assert draft_data["status"] == "unsigned_draft"
    assert draft_data["independently_legally_reviewed"] is False
    doc = client.get(url + "/drafts/" + draft_data["id"] + "/print")
    assert doc.status_code == 200 and "NOT SIGNED" in doc.text
    assert draft_data["sha256"] in doc.text
    assert doc.headers["cache-control"] == "no-store"
    assert open_matter(client, url).status_code == 409


def test_full_case_opening_requires_signed_and_cleared_proof(api, monkeypatch):
    client, who, factory = api
    org, user, url = setup(api, "engagement-full")
    screening(client, url)
    d, clauses = draft(client, url)
    data = mock_pdf(monkeypatch)
    written = upload(client, url, d["id"], data)
    assert written.status_code == 201, written.text
    assert written.json()["scan_status"] == "cleared"
    assert open_matter(client, url).status_code == 409
    assert review(client, url, d["id"]).status_code == 200
    current = client.get(url).json()
    assert current["eligible_for_engagement_gated_case_creation"] is True
    assert current["legal_service_authority_independently_verified"] is False
    bad = open_matter(client, url, professional="nonexistent-consultant")
    assert bad.status_code == 422
    opened = open_matter(client, url)
    assert opened.status_code == 201, opened.text
    assert opened.json()["case_status"] == "draft"
    assert opened.json()["regulated_authority_independently_verified"] is False
    assert opened.json()["professional_sub"] == who["sub"]
    assigned = client.get(url + "/matters").json()
    assert len(assigned) == 1 and assigned[0]["case_id"] == opened.json()["case_id"]
    with factory() as db:
        assert db.query(MatterAssignment).count() == 1
        assert db.query(Case).filter(Case.id == UUID(opened.json()["case_id"])).one().client_id == UUID(user)
        assert db.query(ServiceSignedCopy).one().sha256 == sha256(data).hexdigest()
        events = [x.details for x in db.query(AuditEvent).all()]
        assert "Synthetic reviewed content" not in str(events)
    assert client.post(url + f"/drafts/{d['id']}/review", json={
        "decision": "accept",
        "reviewer_confirmed_signed_terms_and_delivery": True,
        "note": "Do not allow an already accepted signed copy to be rereviewed.",
    }).status_code == 409


def test_change_of_conflict_or_revision_invalidates_previous_acceptance(api, monkeypatch):
    client, _, _ = api
    _, _, url = setup(api, "engagement-stale")
    screening(client, url)
    first, _ = draft(client, url)
    raw = mock_pdf(monkeypatch)
    assert upload(client, url, first["id"], raw).status_code == 201
    assert review(client, url, first["id"]).status_code == 200
    screening(client, url, conflict="unresolved")
    assert client.get(url).json()["eligible_for_engagement_gated_case_creation"] is False
    assert open_matter(client, url).status_code == 409
    screening(client, url)
    assert open_matter(client, url).status_code == 409
    second, _ = draft(client, url)
    assert second["version"] == 2
    assert open_matter(client, url).status_code == 409
    assert review(client, url, first["id"]).status_code == 409


def test_quarantined_pdf_and_rejected_proof_stay_blocked(api, monkeypatch):
    client, _, _ = api
    _, _, url = setup(api, "engagement-quarantine")
    screening(client, url)
    d, _ = draft(client, url)
    raw = mock_pdf(monkeypatch, scan="offline")
    assert upload(client, url, d["id"], raw).json()["scan_status"] == "quarantined"
    assert client.get(url + f"/drafts/{d['id']}/signed-copy").status_code == 423
    assert review(client, url, d["id"]).status_code == 423
    assert client.post(url + f"/drafts/{d['id']}/scan").status_code == 503
    monkeypatch.setattr(engagement, "scan_bytes",
                        lambda content: ScanVerdict(status="cleared"))
    assert client.post(url + f"/drafts/{d['id']}/scan").json()["scan_status"] == "cleared"
    downloaded = client.get(url + f"/drafts/{d['id']}/signed-copy")
    assert downloaded.status_code == 200 and downloaded.content == raw
    assert review(client, url, d["id"], decision="reject").json()["review_status"] == "rejected"
    assert open_matter(client, url).status_code == 409


def test_roles_cross_tenant_and_client_specific_fks(api):
    client, who, factory = api
    org, user, url = setup(api, "engagement-role")
    screening(client, url)
    second = new_client(client, org)
    draft_1, _ = draft(client, url)
    with factory() as db:
        db.add(ServiceAgreementDraft(
            org_id=UUID(org), client_id=UUID(second),
            screen_id=UUID(client.get(url).json()["screen"]["id"]), version=1,
            clauses={}, sha256="1"*64, created_by_sub="test-user-a"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    who["sub"] = "viewer-user"
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="viewer-user", role="viewer", is_active=True))
        db.commit()
    assert client.get(url).status_code == 404
    assert client.post(url + "/screens", json={
        "client_identity_verified": True, "previous_rep_checked": True,
        "prior_rep": "none", "conflict_status": "none_identified",
        "details": "Written fictional review of prior representation and conflicts.",
        "independently_reviewed_conflicts": True}).status_code == 404
    assert open_matter(client, url).status_code == 404
    who["sub"] = "outsider-user"
    assert client.get(url).status_code == 404
    who["sub"] = "test-user-a"
    other_org = new_org(client, "engagement-other-firm")
    assert client.get(url.replace(org, other_org)).status_code == 404


def test_bad_screen_and_missing_client_are_rejected(api):
    client, _, _ = api
    org, user, url = setup(api, "engagement-input")
    assert client.get(url.replace(user, str(uuid4()))).status_code == 404
    invalid = client.post(url + "/screens", json={
        "client_identity_verified": True, "previous_rep_checked": True,
        "prior_rep": "none", "conflict_status": "none_identified",
        "details": "too brief", "independently_reviewed_conflicts": True})
    assert invalid.status_code == 422
    invalid = client.post(url + "/screens", json={
        "client_identity_verified": True, "previous_rep_checked": True,
        "prior_rep": "none", "conflict_status": "none_identified",
        "details": "This is a documented synthetic professional review.",
        "independently_reviewed_conflicts": False})
    assert invalid.status_code == 422
