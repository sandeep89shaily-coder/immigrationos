from uuid import UUID, uuid4

from app.models import AuditEvent, Client, Membership


def new_org(client, slug):
    r = client.post("/api/v1/orgs", json={"name": "Test Firm", "slug": slug})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def new_client(client, org):
    r = client.post(f"/api/v1/orgs/{org}/clients", json={"first_name": "Fictional", "last_name": "Applicant"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_health_and_create_case(api):
    client, who, _ = api
    assert client.get("/health/live").json()["status"] == "ok"
    org = new_org(client, "test-firm-a")
    assert len(client.get("/api/v1/me/orgs").json()) == 1
    cid = new_client(client, org)
    res = client.post(f"/api/v1/orgs/{org}/cases", json={
        "client_id": cid, "application_type": "study_permit", "title": "Test case"})
    assert res.status_code == 201, res.text
    case_id = res.json()["id"]
    change = client.patch(f"/api/v1/orgs/{org}/cases/{case_id}/status",
                          json={"status": "intake", "reason": "Client started questionnaire"})
    assert change.status_code == 200
    assert change.json()["status"] == "intake"
    assert len(client.get(f"/api/v1/orgs/{org}/audit").json()) == 4


def test_tenant_isolation_and_cross_tenant_link_rejected(api):
    client, who, _ = api
    org_a = new_org(client, "alpha-rcic")
    a_client = new_client(client, org_a)
    who["sub"] = "test-user-b"
    assert client.get(f"/api/v1/orgs/{org_a}/clients").status_code == 404
    assert client.get("/api/v1/me/orgs").json() == []
    org_b = new_org(client, "beta-rcic")
    assert client.get(f"/api/v1/orgs/{org_b}/clients").json() == []
    cannot_cross_link = client.post(f"/api/v1/orgs/{org_b}/cases", json={
        "client_id": a_client, "application_type": "visitor", "title": "Cross-tenant case"})
    assert cannot_cross_link.status_code == 404
    assert client.get(f"/api/v1/orgs/{org_a}/clients/{a_client}").status_code == 404


def test_roles_and_audit_access(api):
    client, who, factory = api
    org = new_org(client, "role-check")
    who["sub"] = "test-user-viewer"
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="test-user-viewer", role="viewer", is_active=True))
        db.commit()
    assert client.get(f"/api/v1/orgs/{org}/clients").status_code == 200
    assert client.post(f"/api/v1/orgs/{org}/clients", json={
        "first_name": "Test", "last_name": "Person"}).status_code == 403
    assert client.get(f"/api/v1/orgs/{org}/audit").status_code == 403


def test_status_guard_and_metadata_only_audit(api):
    client, who, factory = api
    org = new_org(client, "status-check")
    cid = new_client(client, org)
    r = client.post(f"/api/v1/orgs/{org}/cases", json={
        "client_id": cid, "application_type": "work_permit", "title": "Example"})
    case = r.json()["id"]
    blocked = client.patch(f"/api/v1/orgs/{org}/cases/{case}/status", json={
        "status": "review", "reason": "Skip verification entirely"})
    assert blocked.status_code == 409
    assert client.get(f"/api/v1/orgs/{org}/audit").status_code == 200
    with factory() as db:
        assert db.query(AuditEvent).filter(AuditEvent.org_id == UUID(org)).count() == 3
        assert "Fictional" not in str([a.details for a in db.query(AuditEvent).all()])


def test_validation_and_duplicate_org_slug(api):
    client, who, _ = api
    new_org(client, "duplicate-slug")
    bad = client.post("/api/v1/orgs", json={"name": "Another", "slug": "duplicate-slug"})
    assert bad.status_code == 409
    assert client.post("/api/v1/orgs", json={"name": "Wrong", "slug": "../abc"}).status_code == 422
    assert client.get(f"/api/v1/orgs/{uuid4()}/cases").status_code == 404
