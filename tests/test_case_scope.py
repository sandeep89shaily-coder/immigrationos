"""Case access, assistant grants and legacy production bypass checks (synthetic)."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.case_scope_models import CaseAccessGrant
from app.models import Membership
from app.settings import get_settings
from tests.test_api import new_org, new_client
from tests.test_engagement import setup, screening, draft, mock_pdf, upload, review, open_matter


def signed_case(api, monkeypatch, slug, professional="test-user-a"):
    client, who, factory = api
    org, client_id, root = setup(api, slug)
    if professional != who["sub"]:
        with factory() as db:
            db.add(Membership(org_id=UUID(org), subject=professional,
                              role="consultant", is_active=True))
            db.commit()
    screening(client, root)
    prepared, _ = draft(client, root)
    contents = mock_pdf(monkeypatch)
    assert upload(client, root, prepared["id"], contents).status_code == 201
    assert review(client, root, prepared["id"]).status_code == 200
    result = open_matter(client, root, professional=professional)
    assert result.status_code == 201, result.text
    return org, client_id, result.json()["case_id"]


def test_legacy_case_cannot_bypass_production_engagement_gate(api, monkeypatch):
    client, _, _ = api
    org = new_org(client, "legacy-blocked")
    cid = new_client(client, org)
    old = client.post(f"/api/v1/orgs/{org}/cases", json={
        "client_id": cid, "title": "Synthetic legacy file",
        "application_type": "study_permit"})
    assert old.status_code == 201
    case_id = old.json()["id"]
    root = f"/api/v1/orgs/{org}/cases/{case_id}"
    assert client.get(f"/api/v1/orgs/{org}/cases").json()[0]["id"] == case_id
    monkeypatch.setattr(get_settings(), "environment", "production")
    assert client.get(root + "/readiness").status_code == 200
    blocked = client.patch(root + "/status", json={
        "status": "intake", "reason": "No service agreement exists"})
    assert blocked.status_code == 409
    assert client.post(root + "/tasks", json={"title": "Cannot bypass engagement"}).status_code == 409
    assert client.post(f"/api/v1/orgs/{org}/cases", json={
        "client_id": cid, "title": "Production bypass attempt",
        "application_type": "study_permit"}).status_code == 409


def test_secondary_firm_staff_cannot_access_unassigned_case(api):
    client, who, factory = api
    org = new_org(client, "unassigned-case")
    cid = new_client(client, org)
    old = client.post(f"/api/v1/orgs/{org}/cases", json={
        "client_id": cid, "title": "Unassigned synthetic draft",
        "application_type": "study_permit"}).json()["id"]
    owner_tasks = client.post(f"/api/v1/orgs/{org}/cases/{old}/tasks",
                              json={"title": "Fictional owner task"})
    assert owner_tasks.status_code == 201

    for sub, role in (("nonprimary-consultant", "consultant"),
                      ("not-granted-assistant", "assistant"),
                      ("read-only-member", "viewer")):
        with factory() as db:
            db.add(Membership(org_id=UUID(org), subject=sub,
                              role=role, is_active=True))
            db.commit()
        who["sub"] = sub
        assert client.get(f"/api/v1/orgs/{org}/cases").json() == []
        assert client.get(f"/api/v1/orgs/{org}/tasks").json() == []
        assert client.get(f"/api/v1/orgs/{org}/issues").json() == []
        assert client.get(f"/api/v1/orgs/{org}/dashboard").json()["cases"] == 0
        for suffix in ("/tasks", "/readiness", "/facts", "/documents",
                       "/reviews/history?filing_context=outside_canada",
                       "/portal/requests", "/study-intake"):
            assert client.get(f"/api/v1/orgs/{org}/cases/{old}"+suffix).status_code == 404, (sub,suffix)
        assert client.post(f"/api/v1/orgs/{org}/cases/{old}/tasks",
                           json={"title": "Attempt unassigned write"}).status_code == 404


def test_current_agreement_assistant_grant_and_revocation(api, monkeypatch):
    client, who, factory = api
    org, client_id, case_id = signed_case(api, monkeypatch, "granted-scope", "primary-consultant")
    root = f"/api/v1/orgs/{org}/cases/{case_id}"
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="assistant-a", role="assistant", is_active=True))
        db.add(Membership(org_id=UUID(org), subject="assistant-b", role="assistant", is_active=True))
        db.commit()

    # An unassigned consultant cannot inspect any case content.
    who["sub"] = "secondary-consultant"
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="secondary-consultant",
                          role="consultant", is_active=True))
        db.commit()
    assert client.get(root + "/facts").status_code == 404
    assert client.get(f"/api/v1/orgs/{org}/cases").json() == []

    who["sub"] = "primary-consultant"
    assert client.get(root + "/facts").status_code == 200
    grant = client.post(root + "/staff/grants", json={
        "subject": "assistant-a", "scope": "read"})
    assert grant.status_code == 201, grant.text
    grant_id = grant.json()["id"]
    assert client.post(root + "/staff/grants", json={
        "subject": "assistant-a", "scope": "read"}).status_code == 409
    assert client.post(root + "/staff/grants", json={
        "subject": "not-a-member", "scope": "intake"}).status_code == 422
    assert client.post(root + "/staff/grants", json={
        "subject": "secondary-consultant", "scope": "read"}).status_code == 422

    who["sub"] = "assistant-a"
    assert client.get(f"/api/v1/orgs/{org}/cases").json()[0]["id"] == case_id
    assert client.get(root + "/facts").status_code == 200
    assert client.get(root + "/documents").status_code == 200
    assert client.post(root + "/tasks", json={
        "title": "Cannot edit with read grant"}).status_code == 403
    assert client.get(root + "/staff/grants").status_code == 403

    who["sub"] = "primary-consultant"
    assert client.post(root + "/staff/grants/"+grant_id+"/revoke").status_code == 200
    assert client.post(root + "/staff/grants/"+grant_id+"/revoke").status_code == 409
    who["sub"] = "assistant-a"
    assert client.get(root + "/facts").status_code == 404
    assert client.get(f"/api/v1/orgs/{org}/cases").json() == []

    who["sub"] = "primary-consultant"
    new = client.post(root + "/staff/grants", json={
        "subject": "assistant-a", "scope": "intake"})
    assert new.status_code == 201, new.text
    who["sub"] = "assistant-a"
    assert client.post(root + "/tasks", json={
        "title": "Permitted synthetic intake follow-up"}).status_code == 201
    assert client.post(root + "/facts", json={
        "field_path": "identity.given_name", "value": "Fictional"}).status_code == 201
    # The assistant is not an authorized professional reviewer.
    assert client.post(root + "/facts/00000000-0000-4000-8000-000000000001/review",
                       json={"status": "verified"}).status_code == 403
    assert client.get(f"/api/v1/orgs/{org}/dashboard").json()["cases"] == 1

    # Offboarding the staff member immediately removes access, even with an active grant.
    who["sub"] = "test-user-a"
    with factory() as db:
        m = db.query(Membership).filter_by(org_id=UUID(org), subject="assistant-a").one()
        m.is_active = False
        db.commit()
    who["sub"] = "assistant-a"
    assert client.get(root + "/facts").status_code == 404


def test_new_conflict_screen_pauses_mutations_in_production(api, monkeypatch):
    client, _, _ = api
    org, client_id, case_id = signed_case(api, monkeypatch, "signed-production")
    root = f"/api/v1/orgs/{org}/cases/{case_id}"
    monkeypatch.setattr(get_settings(), "environment", "production")
    assert client.post(root + "/tasks", json={
        "title": "Current case allowed with staff-reviewed proof"}).status_code == 201
    monkeypatch.setattr(get_settings(), "environment", "test")
    screen = client.post(f"/api/v1/orgs/{org}/engagements/clients/{client_id}/screens",
                         json={"client_identity_verified": True,
                               "previous_rep_checked": True, "prior_rep": "unknown",
                               "conflict_status": "unresolved",
                               "details": "New fictional conflict record requires professional investigation.",
                               "independently_reviewed_conflicts": True})
    assert screen.status_code == 201
    monkeypatch.setattr(get_settings(), "environment", "production")
    assert client.get(root + "/tasks").status_code == 200
    assert client.post(root + "/tasks", json={
        "title": "Blocked due to stale conflict screening"}).status_code == 409


def test_client_directory_and_service_terms_not_firm_wide(api):
    client, who, factory = api
    org = new_org(client, "client-privacy")
    first = new_client(client, org)
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="unrelated-consultant",
                          role="consultant", is_active=True))
        db.add(Membership(org_id=UUID(org), subject="viewer-member",
                          role="viewer", is_active=True))
        db.commit()
    who["sub"] = "unrelated-consultant"
    assert client.get(f"/api/v1/orgs/{org}/clients").json() == []
    assert client.get(f"/api/v1/orgs/{org}/clients/{first}").status_code == 404
    assert client.get(f"/api/v1/orgs/{org}/engagements/clients/{first}").status_code == 404
    assert client.post(f"/api/v1/orgs/{org}/engagements/clients/{first}/screens",
                       json={"client_identity_verified": True,
                             "previous_rep_checked": True, "prior_rep": "none",
                             "conflict_status": "none_identified",
                             "details": "Unrelated professional must not screen this client.",
                             "independently_reviewed_conflicts": True}).status_code == 404
    own = new_client(client, org)
    listing = client.get(f"/api/v1/orgs/{org}/clients").json()
    assert [x["id"] for x in listing] == [own]
    assert client.get(f"/api/v1/orgs/{org}/engagements/clients/{own}").status_code == 200
    who["sub"] = "viewer-member"
    assert client.get(f"/api/v1/orgs/{org}/clients").json() == []
    assert client.get(f"/api/v1/orgs/{org}/clients/{own}").status_code == 404
    who["sub"] = "test-user-a"
    assert len(client.get(f"/api/v1/orgs/{org}/clients").json()) == 2


def test_assistant_can_see_linked_client_but_not_confidential_service_terms(api, monkeypatch):
    client, who, factory = api
    org, c, case_id = signed_case(api, monkeypatch, "client-linked-assistant")
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="linked-assistant",
                          role="assistant", is_active=True))
        db.commit()
    granted = client.post(f"/api/v1/orgs/{org}/cases/{case_id}/staff/grants",
                          json={"subject": "linked-assistant", "scope": "read"})
    assert granted.status_code == 201, granted.text
    who["sub"] = "linked-assistant"
    assert [r["id"] for r in client.get(f"/api/v1/orgs/{org}/clients").json()] == [c]
    assert client.get(f"/api/v1/orgs/{org}/clients/{c}").status_code == 200
    assert client.get(f"/api/v1/orgs/{org}/engagements/clients/{c}").status_code == 404
    assert client.get(f"/api/v1/orgs/{org}/engagements/clients/{c}/history").status_code == 404
    assert client.get(f"/api/v1/orgs/{org}/engagements/cases/{case_id}").status_code == 200
