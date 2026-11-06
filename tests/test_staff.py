"""Synthetic RCIC firm staff invitation, verified-email acceptance and role tests."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID

from app.models import AuditEvent, Membership
from app.staff_models import StaffInvitation
from tests.test_api import new_org


def create(api, slug="staff-verify"):
    client, who, _ = api
    org = new_org(client, slug)
    path = f"/api/v1/orgs/{org}/staff"
    return org, path


def invite(client, url, email="assistant@example.test", role="assistant"):
    return client.post(url + "/invitations", json={"email": email, "role": role})


def switch(who, subject, email, verified=True):
    who.update(sub=subject, email=email, email_verified=verified)


def test_invite_manual_link_accept_replay_and_onboarding(api):
    client, who, factory = api
    org, root = create(api)
    created = invite(client, root)
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["email_sent"] is False and data["role"] == "assistant"
    raw = data["token"]
    with factory() as db:
        entry = db.query(StaffInvitation).one()
        assert entry.token_hash == sha256(raw.encode()).hexdigest()
        assert raw not in str(entry.__dict__)
    pending = client.get(root + "/invitations").json()
    assert len(pending["items"]) == 1
    assert pending["items"][0]["status"] == "pending"
    assert raw not in str(pending)
    assert client.get(root + "/members").json()[0]["role"] == "owner"

    # Wrong email and unverified OIDC account cannot claim the token.
    switch(who, "assistant-id", "different@example.test")
    assert client.post("/api/v1/staff/invitations/accept",
                       json={"token": raw}).status_code == 404
    switch(who, "assistant-id", "assistant@example.test", verified=False)
    assert client.post("/api/v1/staff/invitations/accept",
                       json={"token": raw}).status_code == 403
    switch(who, "assistant-id", "assistant@example.test")
    joined = client.post("/api/v1/staff/invitations/accept", json={"token": raw})
    assert joined.status_code == 200, joined.text
    assert joined.json()["role"] == "assistant"
    assert joined.json()["org_id"] == org
    assert joined.json()["current_rcic_licence_verified"] is False
    assert client.post("/api/v1/staff/invitations/accept",
                       json={"token": raw}).status_code == 404
    assert client.get("/api/v1/me/orgs").json()[0]["role"] == "assistant"
    # An assistant cannot manage firm staff, despite having valid membership.
    assert client.get(root + "/members").status_code == 403
    assert invite(client, root, "other@example.test").status_code == 403
    switch(who, "test-user-a", None)
    staff = client.get(root + "/members").json()
    assert len(staff) == 2
    assert [x for x in staff if x["subject"] == "assistant-id"][0]["verified_email"] == "assistant@example.test"
    assert client.get(root + "/invitations").json()["items"][0]["status"] == "accepted"
    with factory() as db:
        audit_details = str([e.details for e in db.query(AuditEvent).all()])
        assert raw not in audit_details and "assistant@example.test" not in audit_details


def test_expiration_revocation_and_fresh_reissue(api):
    client, who, factory = api
    org, root = create(api, "staff-expire")
    first = invite(client, root).json()
    assert invite(client, root).status_code == 409
    with factory() as db:
        entry = db.query(StaffInvitation).filter_by(id=UUID(first["id"])).one()
        entry.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    switch(who, "pending-id", "assistant@example.test")
    assert client.post("/api/v1/staff/invitations/accept",
                       json={"token": first["token"]}).status_code == 404
    switch(who, "test-user-a", None)
    second = invite(client, root).json()
    assert client.post(root + "/invitations/" + second["id"] + "/revoke").status_code == 200
    assert client.post(root + "/invitations/" + second["id"] + "/revoke").status_code == 409
    switch(who, "pending-id", "assistant@example.test")
    assert client.post("/api/v1/staff/invitations/accept",
                       json={"token": second["token"]}).status_code == 404
    switch(who, "test-user-a", None)
    third = invite(client, root)
    assert third.status_code == 201


def test_admin_governance_role_change_revoke_and_no_owner_escalation(api):
    client, who, factory = api
    org, root = create(api, "staff-governance")
    admin_link = invite(client, root, "admin@example.test", "admin")
    assert admin_link.status_code == 201
    switch(who, "admin-sub", "admin@example.test")
    assert client.post("/api/v1/staff/invitations/accept",
                       json={"token": admin_link.json()["token"]}).status_code == 200
    assert invite(client, root, "newadmin@example.test", "admin").status_code == 403
    assert invite(client, root, "junior@example.test", "assistant").status_code == 201
    assert client.post(root + "/members/test-user-a/revoke").status_code == 403
    assert client.post(root + "/members/test-user-a/role",
                       json={"role": "assistant"}).status_code == 403
    assert client.post(root + "/members/admin-sub/role",
                       json={"role": "consultant"}).status_code == 403
    switch(who, "junior", "junior@example.test")
    # Account deactivation removes all firm membership access without resetting
    # old evidence or creating a new client case.
    switch(who, "test-user-a", None)
    assert client.post(root + "/members/admin-sub/role",
                       json={"role": "consultant"}).status_code == 200
    assert client.post(root + "/members/admin-sub/revoke").status_code == 200
    switch(who, "admin-sub", "admin@example.test")
    assert client.get("/api/v1/me/orgs").json() == []
    assert client.get(root + "/members").status_code == 404
    switch(who, "test-user-a", None)
    members = client.get(root + "/members").json()
    assert [m for m in members if m["subject"] == "admin-sub"][0]["active"] is False
    assert invite(client, root, "admin@example.test", "consultant").status_code == 409


def test_identity_binding_and_cross_firm_scope(api):
    client, who, _ = api
    org_a, first = create(api, "staff-first-org")
    org_b, second = create(api, "staff-second-org")
    one = invite(client, first, "member@example.test", "assistant").json()
    switch(who, "member-b", "member@example.test")
    accepted = client.post("/api/v1/staff/invitations/accept",
                           json={"token": one["token"]})
    assert accepted.status_code == 200 and accepted.json()["org_id"] == org_a
    assert client.get(f"/api/v1/orgs/{org_b}/staff/members").status_code == 404
    switch(who, "test-user-a", None)
    other = invite(client, second, "member@example.test", "viewer")
    assert other.status_code == 201
    switch(who, "member-b", "member@example.test")
    # An existing principal may belong to several firms only through separate
    # email-bound invitations, never through a token for another email.
    accept = client.post("/api/v1/staff/invitations/accept",
                         json={"token": other.json()["token"]})
    assert accept.status_code == 200
    assert {x["id"] for x in client.get("/api/v1/me/orgs").json()} == {org_a, org_b}


def test_viewer_cannot_issue_invites_and_replayed_email_mismatch(api):
    client, who, factory = api
    org, root = create(api, "staff-viewer")
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="viewer-sub",
                          role="viewer", is_active=True))
        db.commit()
    switch(who, "viewer-sub", "viewer@example.test")
    assert client.get(root + "/members").status_code == 403
    assert invite(client, root).status_code == 403
    switch(who, "test-user-a", None)
    invitation = invite(client, root, "member@example.test").json()
    switch(who, "viewer-sub", "viewer@example.test")
    assert client.post("/api/v1/staff/invitations/accept",
                       json={"token": invitation["token"]}).status_code == 404
