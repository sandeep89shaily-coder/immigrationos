"""Version history and case-level service agreement freshness are not conflated."""
from uuid import UUID

from app import engagement
from tests.test_api import new_org, new_client
from tests.test_engagement import setup, screening, draft, mock_pdf, upload, review, open_matter


def test_case_records_its_signed_version_and_detects_later_amendments(api, monkeypatch):
    client, _, _ = api
    org, user, path = setup(api, "engagement-history")
    screening(client, path)
    first, _ = draft(client, path)
    content = mock_pdf(monkeypatch)
    assert upload(client, path, first["id"], content).status_code == 201
    assert review(client, path, first["id"]).status_code == 200
    case = open_matter(client, path)
    assert case.status_code == 201, case.text
    case_url = f"/api/v1/orgs/{org}/engagements/cases/{case.json()['case_id']}"
    current = client.get(case_url)
    assert current.status_code == 200 and current.json()["has_current_reviewed_signed_agreement"] is True
    assert current.json()["agreement_version"] == 1

    history = client.get(path + "/history")
    assert history.status_code == 200 and len(history.json()["drafts"]) == 1
    assert history.json()["drafts"][0]["signed_copy"]["accepted_by_staff"] is True
    assert history.json()["drafts"][0]["screen_still_latest"] is True

    # An unsigned amendment cannot silently replace the agreement attached
    # to the existing case.
    second, _ = draft(client, path)
    assert second["version"] == 2
    stale = client.get(case_url)
    assert stale.status_code == 200
    assert stale.json()["agreement_version"] == 1
    assert stale.json()["latest_agreement_version"] == 2
    assert stale.json()["assigned_agreement_is_latest"] is False
    assert stale.json()["has_current_reviewed_signed_agreement"] is False
    assert stale.json()["requires_professional_reconciliation"] is True

    rows = client.get(path + "/history").json()["drafts"]
    assert [x["version"] for x in rows] == [2, 1]
    assert rows[0]["signed_copy"]["exists"] is False
    assert rows[1]["signed_copy"]["accepted_by_staff"] is True


def test_new_conflict_screen_marks_case_review_stale(api, monkeypatch):
    client, _, _ = api
    org, user, path = setup(api, "engagement-stale-history")
    screening(client, path)
    first, _ = draft(client, path)
    content = mock_pdf(monkeypatch)
    assert upload(client, path, first["id"], content).status_code == 201
    assert review(client, path, first["id"]).status_code == 200
    case = open_matter(client, path).json()
    case_url = f"/api/v1/orgs/{org}/engagements/cases/{case['case_id']}"
    screening(client, path, conflict="unresolved")
    result = client.get(case_url).json()
    assert result["assigned_screen_still_current_and_clear"] is False
    assert result["requires_professional_reconciliation"] is True
    assert result["linked_signed_copy_accepted_by_staff"] is True
    screens = client.get(path + "/history").json()["screens"]
    assert len(screens) == 2
    assert screens[0]["currently_latest"] is True
    assert screens[1]["currently_latest"] is False


def test_legacy_draft_case_is_never_reported_as_engagement_approved(api):
    client, _, _ = api
    org = new_org(client, "legacy-engagement-warning")
    cid = new_client(client, org)
    r = client.post(f"/api/v1/orgs/{org}/cases", json={
        "client_id": cid, "application_type": "study_permit", "title": "Legacy synthetic draft"})
    assert r.status_code == 201
    record = client.get(f"/api/v1/orgs/{org}/engagements/cases/{r.json()['id']}")
    assert record.status_code == 200
    assert record.json()["engagement_link_missing"] is True
    assert record.json()["has_current_reviewed_signed_agreement"] is False


def test_history_and_case_status_cannot_cross_tenants(api):
    client, who, _ = api
    org, user, path = setup(api, "history-tenant")
    screening(client, path)
    who["sub"] = "other-unrelated-principal"
    assert client.get(path + "/history").status_code == 404
    assert client.get(f"/api/v1/orgs/{org}/engagements/cases/00000000-0000-4000-8000-000000000001").status_code == 404
    who["sub"] = "test-user-a"
    other_org = new_org(client, "history-other-tenant")
    assert client.get(path.replace(org, other_org) + "/history").status_code == 404
