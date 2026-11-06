"""Real limited-role PostgreSQL staff invitation acceptance and revocation smoke.

Fictional OIDC verified-email claims are controlled test fixtures; no actual
Keycloak server, mailbox delivery or RCIC licence validation is exercised.
"""
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.auth import Principal, get_principal
from app.db import engine
from app.main import app

who = {"sub": "", "email": None, "verified": False}


def principal():
    return Principal(sub=who["sub"], email=who["email"], email_verified=who["verified"])


def switch(sub, email=None, verified=True):
    who.update(sub=sub, email=email, verified=verified)


app.dependency_overrides[get_principal] = principal

try:
    with engine.connect() as db:
        identity = db.execute(text("""SELECT rolname, rolsuper, rolbypassrls
            FROM pg_roles WHERE rolname=current_user""")).one()
        assert identity[0] == "immigrationos_app" and identity[1:] == (False, False)

    with TestClient(app) as api:
        owner = "owner-" + uuid4().hex
        email = owner + "@example.test"
        switch(owner, email)
        org = api.post("/api/v1/orgs", json={
            "name": "Synthetic Staff Invitation Firm",
            "slug": "verified-staff-" + uuid4().hex,
        })
        assert org.status_code == 201, (org.status_code, org.text)
        org_id = org.json()["id"]
        base = f"/api/v1/orgs/{org_id}/staff"
        uninvited = "uninvited-" + uuid4().hex

        # Direct non-bootstrap insert is rejected by RLS even if the runtime
        # SQL connection sets tenant and subject variables itself.
        with engine.begin() as db:
            db.execute(text("SELECT set_config('app.principal_sub', :sub, true)"),
                       {"sub": uninvited})
            db.execute(text("SELECT set_config('app.tenant_id', :org, true)"),
                       {"org": org_id})
            try:
                with db.begin_nested():
                    db.execute(text("""INSERT INTO memberships
                        (id,org_id,subject,role,is_active,created_at)
                        VALUES(:id,:org,:sub,'owner',true,:now)"""),
                        {"id": uuid4(), "org": org_id, "sub": uninvited,
                         "now": datetime.now(timezone.utc)})
            except SQLAlchemyError:
                pass
            else:
                raise AssertionError("Uninvited membership creation was possible")

        assistant = "assistant-" + uuid4().hex
        assistant_email = assistant + "@example.test"
        invite = api.post(base + "/invitations", json={
            "email": assistant_email, "role": "assistant"})
        assert invite.status_code == 201, (invite.status_code, invite.text)
        token = invite.json()["token"]
        assert api.get(base + "/invitations").json()["items"][0]["status"] == "pending"

        switch(assistant, "not-the-same@example.test")
        assert api.post("/api/v1/staff/invitations/accept",
                        json={"token": token}).status_code == 404
        switch(assistant, assistant_email, False)
        assert api.post("/api/v1/staff/invitations/accept",
                        json={"token": token}).status_code == 403
        switch(assistant, assistant_email)
        accepted = api.post("/api/v1/staff/invitations/accept", json={"token": token})
        assert accepted.status_code == 200, (accepted.status_code, accepted.text)
        assert accepted.json()["org_id"] == org_id
        assert accepted.json()["role"] == "assistant"
        assert accepted.json()["current_rcic_licence_verified"] is False
        assert api.post("/api/v1/staff/invitations/accept",
                        json={"token": token}).status_code == 404
        assert api.get("/api/v1/me/orgs").json()[0]["role"] == "assistant"
        assert api.get(base + "/members").status_code == 403

        switch(owner, email)
        members = api.get(base + "/members")
        assert members.status_code == 200, (members.status_code, members.text)
        assert len(members.json()) == 2
        assert api.get(base + "/invitations").json()["items"][0]["status"] == "accepted"
        assert api.post(base + "/invitations", json={
            "email": assistant_email, "role": "assistant"}).status_code == 409

        admin_sub = "admin-" + uuid4().hex
        admin_email = admin_sub + "@example.test"
        admin_invite = api.post(base + "/invitations", json={
            "email": admin_email, "role": "admin"})
        assert admin_invite.status_code == 201
        switch(admin_sub, admin_email)
        assert api.post("/api/v1/staff/invitations/accept",
                        json={"token": admin_invite.json()["token"]}).status_code == 200
        assert api.post(base + "/invitations", json={
            "email": "other-admin@example.test", "role": "admin"}).status_code == 403
        assert api.post(base + f"/members/{owner}/revoke").status_code == 403
        assert api.post(base + f"/members/{assistant}/role",
                        json={"role": "admin"}).status_code == 403

        switch(owner, email)
        assert api.post(base + f"/members/{assistant}/role",
                        json={"role": "consultant"}).status_code == 200
        assert api.post(base + f"/members/{admin_sub}/revoke").status_code == 200
        assert api.post(base + f"/members/{assistant}/revoke").status_code == 200
        switch(assistant, assistant_email)
        assert api.get("/api/v1/me/orgs").json() == []
        assert api.get(base + "/members").status_code == 404
        switch(admin_sub, admin_email)
        assert api.get("/api/v1/me/orgs").json() == []

finally:
    app.dependency_overrides.clear()

print("PASS: PostgreSQL verified-email invitations, replay defense, role controls and revocation")
