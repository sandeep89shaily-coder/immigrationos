"""Run against the local Docker Compose stack; synthetic data ONLY."""
import os
import uuid
import httpx

BASE = os.getenv("API_BASE", "http://localhost:8000")
KEYCLOAK = os.getenv("DEV_AUTH_URL", "http://localhost:8080/realms/immigrationos-dev/protocol/openid-connect/token")


def main():
    with httpx.Client(timeout=15) as client:
        token_response = client.post(KEYCLOAK, data={
            "grant_type": "password", "client_id": "immigrationos-dev-cli",
            "username": "rcic.demo", "password": "DemoOnly-ChangeMe2026!",
        })
        token_response.raise_for_status()
        access_token = token_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        suffix = uuid.uuid4().hex[:8]
        org_resp = client.post(f"{BASE}/api/v1/orgs", json={"name": "Demo Firm", "slug": f"demo-{suffix}"}, headers=headers)
        org_resp.raise_for_status()
        org = org_resp.json()["id"]
        c = client.post(f"{BASE}/api/v1/orgs/{org}/clients", headers=headers,
                        json={"first_name": "Synthetic", "last_name": "Applicant", "email": "sample@example.invalid"})
        c.raise_for_status()
        case = client.post(f"{BASE}/api/v1/orgs/{org}/cases", headers=headers,
                           json={"client_id": c.json()["id"], "application_type": "study_permit", "title": "Synthetic test case"})
        case.raise_for_status()
        # Exercise core workspace and evidence review APIs with synthetic values.
        case_id = case.json()["id"]
        prefix = f"{BASE}/api/v1/orgs/{org}/cases/{case_id}"
        task = client.post(f"{prefix}/tasks", headers=headers,
                           json={"title": "Collect fictional transcripts"})
        task.raise_for_status()
        fact = client.post(f"{prefix}/facts", headers=headers,
                           json={"field_path": "identity.given_name", "value": "Synthetic"})
        fact.raise_for_status()
        readiness = client.get(f"{prefix}/readiness", headers=headers)
        readiness.raise_for_status()
        workspace = client.get(f"{BASE}/app")
        workspace.raise_for_status()
        assert "ImmigrationOS" in workspace.text
        print(f"PASS: task={task.json()['id']}, fact={fact.json()['id']}, operational_gate={readiness.json()['review_gate']}")
        events = client.get(f"{BASE}/api/v1/orgs/{org}/audit", headers=headers)
        events.raise_for_status()
        print(f"PASS: created org={org}, client={c.json()['id']}, case={case.json()['id']}, audit_events={len(events.json())}")


if __name__ == "__main__":
    main()
