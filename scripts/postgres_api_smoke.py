"""Exercise organization bootstrap and firm isolation through real PostgreSQL APIs.

Run with DATABASE_URL set to the LIMITED app role, after migrations.
This uses synthetic information only and an ephemeral CI database.
"""
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth import Principal, get_principal
from app.main import app

identity = {"sub": ""}

def current_principal():
    return Principal(sub=identity["sub"])

app.dependency_overrides[get_principal] = current_principal
root = "/api/v1/orgs"

try:
    with TestClient(app) as api:
        firms = []
        for code in ("A", "B"):
            identity["sub"] = f"rls-api-{code}-{uuid4()}"
            org = api.post(root, json={"name": f"Synthetic Firm {code}", "slug": f"smoke-{uuid4().hex}"})
            assert org.status_code == 201, f"Firm bootstrap failed: {org.status_code} {org.text}"
            org_id = org.json()["id"]
            customer = api.post(f"{root}/{org_id}/clients", json={"first_name": f"Synthetic{code}", "last_name": "Person"})
            assert customer.status_code == 201, f"Client insert failed: {customer.status_code} {customer.text}"
            case = api.post(f"{root}/{org_id}/cases", json={"client_id": customer.json()["id"], "application_type": "study_permit", "title": "Synthetic Study Permit"})
            assert case.status_code == 201, f"Case insert failed: {case.status_code} {case.text}"
            firms.append((identity["sub"], org_id))

        for user, own_org in firms:
            identity["sub"] = user
            own = api.get(f"{root}/{own_org}/clients")
            assert own.status_code == 200 and len(own.json()) == 1
            other_org = next(org for _, org in firms if org != own_org)
            assert api.get(f"{root}/{other_org}/clients").status_code == 404
            assert api.get(f"{root}/{other_org}/cases").status_code == 404
finally:
    app.dependency_overrides.clear()

print("PASS: PostgreSQL API organization bootstrap, audit write, and firm isolation")
