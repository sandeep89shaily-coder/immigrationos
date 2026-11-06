"""End-to-end fictional RCIC lead → consultation → signed-copy review → conversion."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app import crm
from app.crm_models import (Prospect, ProspectActivity, ConsultationAgreement,
                            ConsultationSignedCopy)
from app.malware_scan import ScannerUnavailable, ScanVerdict
from app.models import AuditEvent, Client, Membership
from tests.test_api import new_org


def lead_payload(**extra):
    return {"first_name": "Fictional", "last_name": "Prospect",
            "email": "fictional.prospect@example.test", "source": "referral",
            "outreach_consent": False, **extra}


def new_lead(api, slug="crm-firm"):
    client, who, db = api
    org = new_org(client, slug)
    res = client.post(f"/api/v1/orgs/{org}/crm/prospects", json=lead_payload())
    assert res.status_code == 201, res.text
    return org, res.json()["id"]


def booking(api, org, prospect):
    client, _, _ = api
    now = datetime.now(timezone.utc) + timedelta(days=2)
    r = client.post(f"/api/v1/orgs/{org}/crm/prospects/{prospect}/consultations", json={
        "starts_at": now.isoformat(), "ends_at": (now + timedelta(minutes=40)).isoformat()})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def agreement(api, org, prospect, appointment):
    client, _, _ = api
    res = client.post(f"/api/v1/orgs/{org}/crm/prospects/{prospect}/consultations/{appointment}/agreements",
        json={"licensee_name": "Consultant Example", "licensee_registration_number": "R000000",
              "licensee_address": "123 Synthetic Road, Ontario", "licensee_phone": "416-555-0001",
              "licensee_email": "professional@example.test", "client_address": "8 Fictional Avenue, Ontario",
              "purpose_scope": "Discuss a fictional applicant's options and information-gathering steps.",
              "regulator_description": "The College is the statutory regulator overseeing its licensees.",
              "fee_cents_cad": 0, "pro_bono": True})
    assert res.status_code == 201, res.text
    return res.json()


def proof_path(org, prospect, appointment, agreement_id):
    return (f"/api/v1/orgs/{org}/crm/prospects/{prospect}/consultations/"
            f"{appointment}/agreements/{agreement_id}")


def fake_pdf(monkeypatch, *, scan="cleared"):
    data = b"%PDF-1.4\nSynthetic dummy signed-document fixture\n%%EOF\n"
    monkeypatch.setattr(crm, "save_blob", lambda contents, mime: ("1"*32, sha256(contents).hexdigest()))
    monkeypatch.setattr(crm, "load_blob", lambda key: data)
    monkeypatch.setattr(crm, "delete_failed_blob", lambda key: None)
    if scan == "unavailable":
        def unavailable(data):
            raise ScannerUnavailable("scanner offline")
        monkeypatch.setattr(crm, "scan_bytes", unavailable)
    else:
        monkeypatch.setattr(crm, "scan_bytes", lambda contents: ScanVerdict(status=scan))
    return data


def upload_proof(client, path, contents):
    signed = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    delivered = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    return client.post(path + "/signed-copy", data={
        "signed_at": signed, "client_copy_provided_at": delivered,
    }, files={"file": ("fictional-signed.pdf", contents, "application/pdf")})


def review_proof(client, path, *, decision="accept", attested=True):
    return client.post(path + "/review", json={
        "decision": decision,
        "reviewer_attests_signed_agreement_and_client_copy": attested,
        "review_note": "Synthetic signed copy reviewed and client-delivery evidence checked."})


def test_lead_creation_contact_logging_and_duplicate_handling(api):
    client, _, factory = api
    org, lead = new_lead(api)
    base = f"/api/v1/orgs/{org}/crm/prospects"
    assert len(client.get(base).json()) == 1
    assert client.post(base, json=lead_payload()).status_code == 409
    assert client.post(base, json=lead_payload(email=None, phone=None)).status_code == 422
    assert client.post(base, json=lead_payload(outreach_consent=True)).status_code == 422
    r = client.post(base + f"/{lead}/activities", json={
        "kind": "email", "content": "Fictional intake email was sent outside this system."})
    assert r.status_code == 201
    assert r.json()["message_sent"] is False
    assert client.get(base + f"/{lead}").json()["stage"] == "contacted"
    activities = client.get(base + f"/{lead}/activities").json()
    assert len(activities) == 1 and activities[0]["kind"] == "email"
    with factory() as db:
        assert db.query(ProspectActivity).count() == 1
        history = [e.details for e in db.query(AuditEvent).all()]
        assert "fictional.prospect@example.test" not in str(history)


def test_booking_and_consultation_cannot_complete_without_signed_terms(api):
    client, _, _ = api
    org, lead = new_lead(api, "crm-book")
    appt = booking(api, org, lead)
    base = f"/api/v1/orgs/{org}/crm/prospects/{lead}/consultations"
    assert client.post(base, json={
        "starts_at": "2026-11-30T10:00:00", "ends_at": "2026-11-30T11:00:00"}).status_code == 422
    assert client.post(base + f"/{appt}/complete").status_code == 409
    assert client.post(f"/api/v1/orgs/{org}/crm/prospects/{lead}/convert").status_code == 409
    form = agreement(api, org, lead, appt)
    assert form["version"] == 1 and form["status"] == "draft_not_signed"
    assert form["terms"]["not_approved_legal_template"] is True
    assert form["delivery_and_e_signature_not_implemented"] is True
    assert len(form["terms_sha256"]) == 64
    assert client.post(base + f"/{appt}/complete").status_code == 409
    assert client.get(base + f"/{appt}/agreements").json()[0]["version"] == 1


def test_full_fictional_flow_requires_scan_and_professional_review(api, monkeypatch):
    client, _, factory = api
    org, lead = new_lead(api, "crm-full")
    appt = booking(api, org, lead)
    form = agreement(api, org, lead, appt)
    path = proof_path(org, lead, appt, form["id"])
    data = fake_pdf(monkeypatch)
    uploaded = upload_proof(client, path, data)
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["scan_status"] == "cleared"
    assert uploaded.json()["human_review_required"] is True
    assert client.post(f"/api/v1/orgs/{org}/crm/prospects/{lead}/consultations/{appt}/complete").status_code == 409
    assert review_proof(client, path, attested=False).status_code == 422
    verdict = review_proof(client, path)
    assert verdict.status_code == 200, verdict.text
    assert verdict.json()["review_status"] == "accepted"
    assert verdict.json()["external_signature_cryptography_verified"] is False
    assert client.post(path + "/review", json={
        "decision": "accept", "reviewer_attests_signed_agreement_and_client_copy": True,
        "review_note": "Review cannot be repeated for an already reviewed copy."}).status_code == 409
    completed = client.post(f"/api/v1/orgs/{org}/crm/prospects/{lead}/consultations/{appt}/complete")
    assert completed.status_code == 200, completed.text
    assert completed.json()["further_services_require_separate_service_agreement"] is True
    converted = client.post(f"/api/v1/orgs/{org}/crm/prospects/{lead}/convert")
    assert converted.status_code == 201, converted.text
    assert converted.json()["created"] is True
    client_id = converted.json()["client_id"]
    repeat = client.post(f"/api/v1/orgs/{org}/crm/prospects/{lead}/convert")
    assert repeat.status_code == 201 and repeat.json()["created"] is False
    assert repeat.json()["client_id"] == client_id
    assert client.get(f"/api/v1/orgs/{org}/clients/{client_id}").json()["first_name"] == "Fictional"
    with factory() as db:
        assert db.query(Client).count() == 1
        assert db.query(Prospect).one().converted_client_id == UUID(client_id)
        saved = db.query(ConsultationSignedCopy).one()
        assert saved.review_status == "accepted"
        assert saved.review_note.startswith("Synthetic signed")
        assert saved.sha256 == sha256(data).hexdigest()


def test_quarantine_stays_blocked_until_real_scan(api, monkeypatch):
    client, _, _ = api
    org, lead = new_lead(api, "crm-quarantine")
    appt = booking(api, org, lead)
    form = agreement(api, org, lead, appt)
    path = proof_path(org, lead, appt, form["id"])
    data = fake_pdf(monkeypatch, scan="unavailable")
    uploaded = upload_proof(client, path, data)
    assert uploaded.status_code == 201 and uploaded.json()["scan_status"] == "quarantined"
    assert review_proof(client, path).status_code == 423
    assert client.post(path + "/scan").status_code == 503
    monkeypatch.setattr(crm, "scan_bytes", lambda content: ScanVerdict(status="cleared"))
    assert client.post(path + "/scan").json()["scan_status"] == "cleared"
    assert review_proof(client, path).status_code == 200
    assert client.post(f"/api/v1/orgs/{org}/crm/prospects/{lead}/consultations/{appt}/complete").status_code == 200


def test_rejected_signed_copy_cannot_complete_or_be_replaced_silently(api, monkeypatch):
    client, _, _ = api
    org, lead = new_lead(api, "crm-rejected")
    appt = booking(api, org, lead)
    form = agreement(api, org, lead, appt)
    path = proof_path(org, lead, appt, form["id"])
    data = fake_pdf(monkeypatch)
    assert upload_proof(client, path, data).status_code == 201
    assert review_proof(client, path, decision="reject").json()["review_status"] == "rejected"
    assert client.post(f"/api/v1/orgs/{org}/crm/prospects/{lead}/consultations/{appt}/complete").status_code == 409
    assert upload_proof(client, path, data).status_code == 409
    assert client.post(f"/api/v1/orgs/{org}/crm/prospects/{lead}/consultations/{appt}/agreements", json={
        "licensee_name": "Consultant Example", "licensee_registration_number": "R000000",
        "licensee_address": "123 Synthetic Road, Ontario", "licensee_phone": "416-555-0001",
        "licensee_email": "professional@example.test", "client_address": "8 Fictional Avenue, Ontario",
        "purpose_scope": "A new version after rejected proof should start a new appointment.",
        "regulator_description": "The College is the statutory regulator overseeing its licensees.",
        "fee_cents_cad": 0, "pro_bono": True}).status_code == 409


def test_permissions_and_cross_firm_and_cross_prospect(api, monkeypatch):
    client, who, factory = api
    org, lead = new_lead(api, "crm-tenant-one")
    appt = booking(api, org, lead)
    form = agreement(api, org, lead, appt)
    fake_pdf(monkeypatch)
    other_lead = client.post(f"/api/v1/orgs/{org}/crm/prospects", json={
        **lead_payload(email="second@example.test")}).json()["id"]
    wrong = proof_path(org, other_lead, appt, form["id"])
    assert upload_proof(client, wrong, b"%PDF-1.4\nsynthetic\n%%EOF").status_code == 404

    who["sub"] = "test-viewer"
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="test-viewer", role="viewer", is_active=True))
        db.commit()
    assert client.get(f"/api/v1/orgs/{org}/crm/prospects").status_code == 200
    assert client.post(f"/api/v1/orgs/{org}/crm/prospects", json=lead_payload(email="third@example.test")).status_code == 403
    assert client.post(f"/api/v1/orgs/{org}/crm/prospects/{lead}/consultations", json={
        "starts_at": datetime.now(timezone.utc).isoformat(),
        "ends_at": (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()}).status_code == 403

    who["sub"] = "outsider"
    assert client.get(f"/api/v1/orgs/{org}/crm/prospects").status_code == 404
    assert client.get(f"/api/v1/orgs/{org}/crm/prospects/{lead}").status_code == 404
    who["sub"] = "test-user-a"
    org2 = new_org(client, "crm-tenant-two")
    assert client.get(f"/api/v1/orgs/{org2}/crm/prospects/{lead}").status_code == 404


def test_composite_db_constraints_block_cross_prospect_links(api):
    client, _, factory = api
    org, lead = new_lead(api, "crm-fk")
    appt = booking(api, org, lead)
    other_lead = client.post(f"/api/v1/orgs/{org}/crm/prospects",
        json=lead_payload(email="second-prospect@example.test")).json()["id"]
    with factory() as db:
        from app.crm_models import ConsultationAgreement
        db.add(ConsultationAgreement(org_id=UUID(org), prospect_id=UUID(other_lead),
                                    consultation_id=UUID(appt), version=1, terms={},
                                    terms_sha256="a"*64, created_by_sub="test-user-a"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
