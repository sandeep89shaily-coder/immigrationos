"""Prospect next-action queue: deduplication, overdue status and role isolation."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.crm_models import ProspectFollowUp
from app.models import AuditEvent, Membership
from tests.test_crm import new_lead
from tests.test_api import new_org


def root(org, prospect):
    return f"/api/v1/orgs/{org}/crm/prospects/{prospect}/follow-ups"


def payload(*, days=2, title="Follow up on initial consultation", priority="normal"):
    return {
        "title": title,
        "due_at": (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(),
        "priority": priority,
    }


def test_create_read_complete_and_deduplicate_followup(api):
    client, who, factory = api
    org, prospect = new_lead(api, "crm-followup-01")
    url = root(org, prospect)
    created = client.post(url, json=payload())
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["assigned_to_sub"] == "test-user-a"
    assert item["delivery_mode"] == "internal_queue_only"
    assert item["message_sent"] is False
    assert item["overdue"] is False
    assert client.post(url, json=payload(title="follow up on initial consultation")).status_code == 409
    assert len(client.get(url).json()) == 1
    firm = client.get(f"/api/v1/orgs/{org}/crm/follow-ups?status=open").json()
    assert len(firm["items"]) == 1 and firm["automated_reminders_enabled"] is False
    completed = client.post(url + f"/{item['id']}/complete")
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"] is not None
    assert client.post(url + f"/{item['id']}/complete").status_code == 409
    assert client.post(url + f"/{item['id']}/cancel").status_code == 409
    assert client.get(f"/api/v1/orgs/{org}/crm/follow-ups").json()["items"] == []
    assert len(client.get(f"/api/v1/orgs/{org}/crm/follow-ups?status=completed").json()["items"]) == 1
    with factory() as db:
        event = db.query(AuditEvent).filter(AuditEvent.action == "crm.followup_completed").one()
        assert "consultation" not in str(event.details).lower()


def test_overdue_queue_uses_actual_due_date_and_excludes_closed_items(api):
    client, _, factory = api
    org, prospect = new_lead(api, "crm-followup-02")
    url = root(org, prospect)
    first = client.post(url, json=payload(title="Call back about documents")).json()
    second = client.post(url, json=payload(title="Request fictional forms")).json()
    with factory() as db:
        row = db.query(ProspectFollowUp).filter_by(id=UUID(first["id"])).one()
        row.due_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
    overdue = client.get(f"/api/v1/orgs/{org}/crm/follow-ups?overdue_only=true").json()
    assert [x["id"] for x in overdue["items"]] == [first["id"]]
    assert overdue["items"][0]["overdue"] is True
    cancelled = client.post(url + f"/{first['id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert client.get(f"/api/v1/orgs/{org}/crm/follow-ups?overdue_only=true").json()["items"] == []
    assert client.get(f"/api/v1/orgs/{org}/crm/follow-ups").json()["items"][0]["id"] == second["id"]


def test_validation_is_timezone_aware_and_no_unapproved_reminders(api):
    client, _, _ = api
    org, prospect = new_lead(api, "crm-followup-03")
    url = root(org, prospect)
    now = datetime.now(timezone.utc)
    for bad in [
        {**payload(), "due_at": "2026-11-09T10:00:00"},
        {**payload(), "due_at": (now - timedelta(hours=1)).isoformat()},
        {**payload(), "due_at": (now + timedelta(days=1500)).isoformat()},
        payload(priority="catastrophic"),
        payload(title="    "),
    ]:
        assert client.post(url, json=bad).status_code == 422
    assert client.get(f"/api/v1/orgs/{org}/crm/follow-ups").json()["items"] == []


def test_access_and_closed_prospect_creation_gates(api):
    client, who, factory = api
    org, prospect = new_lead(api, "crm-followup-04")
    url = root(org, prospect)
    created = client.post(url, json=payload()).json()
    who["sub"] = "read-only-viewer"
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="read-only-viewer",
                          role="viewer", is_active=True))
        db.commit()
    assert client.get(url).status_code == 200
    assert client.post(url, json=payload(title="Second call")).status_code == 403
    assert client.post(url + f"/{created['id']}/complete").status_code == 403
    who["sub"] = "not-a-member"
    assert client.get(f"/api/v1/orgs/{org}/crm/follow-ups").status_code == 404
    assert client.get(url).status_code == 404
    who["sub"] = "test-user-a"
    other_org = new_org(client, "crm-followup-other-firm")
    assert client.get(root(other_org, prospect)).status_code == 404
    assert client.post(f"/api/v1/orgs/{org}/crm/prospects/{prospect}/close", json={
        "reason": "Close attempt while follow-up is open"
    }).status_code == 200
    assert client.post(url, json=payload(title="Follow up after closure")).status_code == 409
    # Existing task remains visible and can be explicitly cancelled after closure.
    assert client.post(url + f"/{created['id']}/cancel").status_code == 200


def test_cross_prospect_followup_fk_does_not_allow_forged_association(api):
    client, _, factory = api
    org, prospect = new_lead(api, "crm-followup-05")
    second = client.post(f"/api/v1/orgs/{org}/crm/prospects", json={
        "first_name":"Other","last_name":"Fictional","email":"other@example.test",
        "source":"referral"}).json()["id"]
    with factory() as db:
        # Nonexistent prospect ID cannot pass the case-like tenant FK.
        db.add(ProspectFollowUp(org_id=UUID(org), prospect_id=uuid4(), title="Forged lead",
                                due_at=datetime.now(timezone.utc) + timedelta(hours=2),
                                priority="normal", status="open",
                                assigned_to_sub="test-user-a", created_by_sub="test-user-a"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    assert client.get(root(org, prospect)).status_code == 200
    assert client.get(root(org, second)).status_code == 200
