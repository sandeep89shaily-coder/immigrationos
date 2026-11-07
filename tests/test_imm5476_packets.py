"""Immutable IMM5476 review checkpoints: case isolation and fail-closed snapshots."""
from uuid import UUID, uuid4

from app import imm5476_packets as packets
from app.models import Case, CaseDocument, CaseFact, CaseIssue, Membership
from app.imm5476_packet_models import IMM5476ReviewPacket
from tests.test_imm5476_case_preview import make_case
from tests.test_application_package import start


def configured(api, slug, *, rep=True):
    client, who, factory = api
    org, case, base = make_case(api, slug)
    root = f"/api/v1/orgs/{org}/cases/{case}"
    assert start(client, root + "/package", representative=rep).status_code == 201
    return org, case, base, root + "/ircc/IMM5476/packets"


def reviewed(api, org, case, fields=2):
    _, _, factory = api
    doc_id = uuid4()
    with factory() as db:
        db.add(CaseDocument(
            id=doc_id, org_id=UUID(org), case_id=UUID(case),
            filename="fictional-reviewed-file.pdf", document_type="passport",
            mime_type="application/pdf", size_bytes=100, sha256="b"*64,
            storage_key=uuid4().hex, uploaded_by_sub="test-user-a"))
        keys = list(packets.current_snapshot.__globals__["build_preview"].__globals__["CANONICAL_FIELDS"].values())
        for i, path in enumerate(keys[:fields]):
            db.add(CaseFact(
                org_id=UUID(org), case_id=UUID(case), document_id=doc_id,
                field_path=path, value=f"Fictional-{i}",
                review_status="verified", reviewed_by_sub="test-user-a",
                created_by_sub="test-user-a"))
        db.commit()
    return doc_id


def capture(client, endpoint, sha, ack=True):
    return client.post(endpoint, json={
        "expected_sha256": sha, "acknowledge_internal_only": ack})


def test_requires_selected_representative_form(api):
    client, _, factory = api
    org, case, preview, endpoint = configured(api, "imm5476-pkt-no-rep", rep=False)
    assert client.get(endpoint).status_code == 409
    assert capture(client, endpoint, "0"*64).status_code == 409
    with factory() as db:
        assert db.query(IMM5476ReviewPacket).count() == 0


def test_no_verified_field_cannot_create_checkpoint(api):
    client, _, _ = api
    org, case, preview, endpoint = configured(api, "imm5476-pkt-empty")
    assert client.get(endpoint).json() == []
    snapshot = client.get(preview).json()
    assert snapshot["verified_text_fields"] == 0
    assert capture(client, endpoint, snapshot["snapshot_sha256"], ack=False).status_code == 422
    assert capture(client, endpoint, "0"*64).status_code == 409
    assert capture(client, endpoint, snapshot["snapshot_sha256"]).status_code == 409


def test_partial_review_packet_is_immutable_and_stale_on_change(api, monkeypatch):
    client, who, factory = api
    org, case, preview, endpoint = configured(api, "imm5476-pkt-partial")
    doc_id = reviewed(api, org, case, fields=2)
    monkeypatch.setattr(packets, "scan_status_by_document",
                        lambda *args: {doc_id: "cleared"})
    snapshot = client.get(preview).json()
    # Preview has its own independent scan reader, which is not patched.
    # Packet capture must match the recomputed server-side snapshot hash.
    from app import imm5476_case_preview as live
    monkeypatch.setattr(live, "scan_status_by_document",
                        lambda *args: {doc_id: "cleared"})
    # Endpoint imported scan_status_by_document at module import and the
    # mutation above intentionally does not affect it.
    direct = packets.current_snapshot
    with factory() as db:
        package, live_report = direct(db, UUID(org), UUID(case))
    response = capture(client, endpoint, live_report["snapshot_sha256"])
    assert response.status_code == 201, response.text
    packet = response.json()
    assert packet["form_code"] == "IMM5476"
    assert packet["verified_observed_subset"] is False
    assert packet["is_current"] is True
    assert packet["submission_supported"] is False
    assert len(packet["fields"]) == 21
    assert len([f for f in packet["fields"] if f["status"] == "verified_source_value"]) == 2
    assert len([f for f in packet["fields"] if f["status"] == "missing_evidence"]) == 19
    assert not [f for f in packet["fields"] if f["status"] != "verified_source_value" and f["value"]]
    assert capture(client, endpoint, live_report["snapshot_sha256"]).status_code == 409
    with factory() as db:
        fact = db.query(CaseFact).filter(
            CaseFact.org_id == UUID(org), CaseFact.case_id == UUID(case)).first()
        fact.value = "New fictional value"
        db.commit()
    after = client.get(endpoint)
    assert after.status_code == 200
    history = after.json()
    assert len(history) == 1 and history[0]["is_current"] is False
    assert history[0]["fields"] == packet["fields"]
    with factory() as db:
        assert db.query(IMM5476ReviewPacket).count() == 1
    assert client.post(endpoint, json={
        "expected_sha256": live_report["snapshot_sha256"],
        "acknowledge_internal_only": True}).status_code == 409


def test_unsafe_scan_and_unreviewed_evidence_are_rejected(api, monkeypatch):
    client, _, factory = api
    org, case, preview, endpoint = configured(api, "imm5476-pkt-block-unsafe")
    doc_id = reviewed(api, org, case, fields=2)
    snapshot = client.get(preview).json()
    with factory() as db:
        _, report = packets.current_snapshot(db, UUID(org), UUID(case))
    assert report["verified_text_fields"] == 0
    assert capture(client, endpoint, report["snapshot_sha256"]).status_code == 409
    monkeypatch.setattr(packets, "scan_status_by_document",
                        lambda *args: {doc_id: "cleared"})
    with factory() as db:
        fact = db.query(CaseFact).filter(
            CaseFact.case_id == UUID(case)).first()
        fact.review_status = "pending"
        fact.reviewed_by_sub = None
        db.commit()
        _, report = packets.current_snapshot(db, UUID(org), UUID(case))
    assert report["verified_text_fields"] == 1
    assert "unreviewed_evidence" in {f["status"] for f in report["fields"]}
    assert capture(client, endpoint, report["snapshot_sha256"]).status_code == 409


def test_closed_case_open_issue_unassigned_and_viewer_denials(api, monkeypatch):
    client, who, factory = api
    org, case, preview, endpoint = configured(api, "imm5476-pkt-permissions")
    doc_id = reviewed(api, org, case, fields=1)
    monkeypatch.setattr(packets, "scan_status_by_document",
                        lambda *args: {doc_id: "cleared"})
    with factory() as db:
        _, report = packets.current_snapshot(db, UUID(org), UUID(case))
        db.add(Membership(org_id=UUID(org), subject="unassigned-viewer",
                          role="viewer", is_active=True))
        db.commit()
    who["sub"] = "unassigned-viewer"
    assert client.get(endpoint).status_code == 404
    assert capture(client, endpoint, report["snapshot_sha256"]).status_code == 404
    who["sub"] = "test-user-a"
    with factory() as db:
        c = db.query(Case).filter(Case.id == UUID(case)).one()
        c.status = "closed"
        db.commit()
        _, new_report = packets.current_snapshot(db, UUID(org), UUID(case))
    assert capture(client, endpoint, new_report["snapshot_sha256"]).status_code == 409
    with factory() as db:
        c = db.query(Case).filter(Case.id == UUID(case)).one()
        c.status = "review"
        db.add(CaseIssue(org_id=UUID(org), case_id=UUID(case),
                         fingerprint="1"*64, issue_type="contradiction",
                         field_path="identity.family_name",
                         description="Fictional contradiction", severity="review",
                         status="open"))
        db.commit()
        _, issue_report = packets.current_snapshot(db, UUID(org), UUID(case))
    assert capture(client, endpoint, issue_report["snapshot_sha256"]).status_code == 409
