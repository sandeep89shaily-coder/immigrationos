"""Synthetic history timeline checks; no assumed IRCC coverage window."""
from datetime import date
from uuid import UUID, uuid4

from app.applicant_history_models import ApplicantHistory
from app.history_timeline_audit import audit_history_timeline
from app.models import Membership
from tests.test_applicant_histories import context


def _entry(org, client, kind, start, end, version=1):
    details = {"start_date": start}
    if end is not None:
        details["end_date"] = end
    return ApplicantHistory(id=uuid4(), org_id=org, client_id=client,
                            kind=kind, details=details,
                            version=version, updated_by_sub="synthetic")


def _find(report, kind, flag_type):
    return [flag for flag in report["categories"][kind]["flags"]
            if flag["type"] == flag_type]


def test_overlap_and_inclusive_gaps_are_mechanical_prompts_only():
    org, client = uuid4(), uuid4()
    rows = [
        _entry(org, client, "address", "2022-01-01", "2022-03-31"),
        _entry(org, client, "address", "2022-03-31", "2022-04-30"),
        _entry(org, client, "address", "2022-06-01", "2022-12-31"),
        _entry(org, client, "employment", "2022-01-01", "2022-12-31"),
    ]
    result = audit_history_timeline(
        records=rows, client_id=client, org_id=org,
        start=date(2022, 1, 1), end=date(2022, 12, 31))
    assert len(_find(result, "address", "overlap_for_review")) == 1
    gaps = _find(result, "address", "uncovered_period_for_review")
    assert [(x["start_date"], x["end_date"]) for x in gaps] == [
        ("2022-05-01", "2022-05-31")]
    assert _find(result, "employment", "uncovered_period_for_review") == []
    assert result["timeline_complete_for_ircc"] is False
    assert result["all_histories_verified"] is False
    assert result["window_selected_by"] == "requester_not_ircc_rule"


def test_unknown_end_does_not_produce_fake_gaps_or_certify_coverage():
    org, client = uuid4(), uuid4()
    rows = [_entry(org, client, "address", "2021-01-01", None),
            _entry(org, client, "address", "2022-05-01", "2022-06-01")]
    result = audit_history_timeline(
        records=rows, client_id=client, org_id=org,
        start=date(2021, 1, 1), end=date(2023, 1, 1))
    assert len(_find(result, "address", "end_date_not_supplied")) == 1
    assert not _find(result, "address", "uncovered_period_for_review")
    assert result["categories"]["address"]["coverage_evaluable"] is False


def test_invalid_legacy_dates_and_cross_client_rows_do_not_leak():
    org, client, other_org, other_client = uuid4(), uuid4(), uuid4(), uuid4()
    rows = [_entry(org, client, "education", "impossible", "2022-01-01"),
            _entry(org, client, "education", "2023-01-01", "2022-01-01"),
            _entry(other_org, client, "address", "2022-01-01", "2022-12-31"),
            _entry(org, other_client, "employment", "2022-01-01", "2022-12-31")]
    result = audit_history_timeline(
        records=rows, client_id=client, org_id=org,
        start=date(2022, 1, 1), end=date(2022, 12, 31))
    assert len(_find(result, "education", "invalid_date")) == 1
    assert len(_find(result, "education", "reversed_period")) == 1
    assert result["categories"]["address"]["record_count"] == 0
    assert result["categories"]["employment"]["record_count"] == 0


def test_snapshot_changes_after_history_version_or_value_update():
    org, client = uuid4(), uuid4()
    row = _entry(org, client, "employment", "2022-01-01", "2022-12-31")
    args = dict(client_id=client, org_id=org,
                start=date(2022, 1, 1), end=date(2022, 12, 31))
    first = audit_history_timeline(records=[row], **args)
    row.version += 1
    row.details = {**row.details, "end_date": "2022-10-31"}
    second = audit_history_timeline(records=[row], **args)
    assert first["snapshot_sha256"] != second["snapshot_sha256"]
    assert len(second["categories"]["employment"]["flags"]) == 1


def test_tenant_case_scope_read_only_api_and_bad_window(api):
    client, who, factory = api
    org, case, cid, histories_url = context(api, "timeline-audit-api")
    created = client.post(histories_url + "/address", json={"details": {
        "start_date": "2023-01-01", "end_date": "2023-03-31",
        "line1": "1 Fake Way", "city": "Example City", "country": "Fictionland"
    }})
    assert created.status_code == 201, created.text
    route = f"/api/v1/orgs/{org}/cases/{case}/history-timeline-audit"
    query = "?start_date=2023-01-01&end_date=2023-12-31"
    response = client.get(route + query)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["categories"]["address"]["record_count"] == 1
    assert any(f["start_date"] == "2023-04-01" for f in
               _find(data, "address", "uncovered_period_for_review"))
    assert "1 Fake Way" not in str(data)
    assert client.get(route).status_code == 422
    assert client.get(route + "?start_date=2024-01-01&end_date=2023-01-01").status_code == 422
    with factory() as db:
        db.add(Membership(org_id=UUID(org), subject="unassigned-audit",
                          role="consultant", is_active=True))
        db.commit()
    who["sub"] = "unassigned-audit"
    assert client.get(route + query).status_code == 404
    who["sub"] = "outsider-audit"
    assert client.get(route + query).status_code == 404
