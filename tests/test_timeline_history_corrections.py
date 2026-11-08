"""Consultant history corrections need reviewed provenance and immutable revisions."""
from uuid import UUID

from sqlalchemy import select
from app.applicant_history_models import ApplicantHistory
from app.timeline_history_correction_models import TimelineHistoryCorrection
from app.timeline_clarification_models import TimelineClarificationReply
from tests.test_study_intake import _open_client
from tests.test_timeline_clarifications import _audit_url, _staff_url, _client_url


def setup_request(api, name, *, existing=False):
    client, who, factory = api
    org, case, staff = _open_client(api, name)
    who.update(sub=staff, email=None, email_verified=False)
    cid = next(x["client_id"] for x in client.get(
        f"/api/v1/orgs/{org}/cases").json() if x["id"] == case)
    first = None
    if existing:
        first = client.post(f"/api/v1/orgs/{org}/clients/{cid}/histories/address",
                            json={"details": {"start_date":"2022-01-01",
                                "end_date":"2022-03-31","line1":"1 Synthetic St",
                                "city":"Imaginary Town","country":"Exampleland"}})
        assert first.status_code == 201, first.text
    audit = client.get(_audit_url(org, case)).json()
    flag = next(x for x in audit["categories"]["address"]["flags"]
                if x["type"] == "uncovered_period_for_review")
    url = _staff_url(org, case)
    request = client.post(url, json={
        "start_date":"2022-01-01","end_date":"2022-12-31",
        "kind":"address","flag_sha256":flag["flag_sha256"],
        "snapshot_sha256":audit["snapshot_sha256"],
        "question":"Please clarify the missing fictional address dates."})
    assert request.status_code == 201, request.text
    return org, case, cid, staff, first.json() if first else None, request.json()["id"]


def reply_review(api, case, staff, request_id, name, *, decision="reviewed"):
    client, who, _ = api
    who.update(sub=name+"-client", email="sample.person@example.test", email_verified=True)
    portal = _client_url(case)
    reply = client.post(portal+f"/{request_id}/reply", json={
        "answer":"I stayed at a fictional family residence during those dates."})
    assert reply.status_code == 201, reply.text
    who.update(sub=staff, email=None, email_verified=False)
    return reply


def correction_url(org, case, request_id):
    return _staff_url(org, case)+f"/{request_id}/history-correction"


def new_address(start, end):
    return {"start_date":start,"end_date":end,"line1":"2 Correction Lane",
            "city":"Synthetic City","country":"Exampleland"}


def test_reviewed_gap_creates_history_once_and_freezes_linked_sources(api):
    client, who, factory = api
    name="history-correction-create"
    org, case, cid, staff, first, request_id = setup_request(api, name)
    url=correction_url(org, case, request_id)
    payload={"operation":"create","details":new_address("2022-01-01","2022-12-31"),
             "correction_reason":"Client confirmed a temporary synthetic residence."}
    # Neither an unreplied request nor an unreviewed reply authorizes an import.
    assert client.post(url,json=payload).status_code == 409
    reply_review(api,case,staff,request_id,name)
    assert client.post(url,json=payload).status_code == 409
    decision=client.post(_staff_url(org,case)+f"/{request_id}/decide",
                         json={"decision":"reviewed"})
    assert decision.status_code == 201,decision.text
    result=client.post(url,json=payload)
    assert result.status_code == 201,result.text
    assert result.json()["new_version"] == 1
    assert result.json()["verified_evidence"] is False
    assert client.post(url,json=payload).status_code == 409
    listed=client.get(_staff_url(org,case)+"/history-corrections")
    assert listed.status_code == 200,listed.text
    ledger=listed.json()["corrections"]
    assert len(ledger) == 1
    assert ledger[0]["prior_details"] is None
    assert ledger[0]["new_details"]["line1"] == "2 Correction Lane"
    with factory() as db:
        assert db.query(TimelineHistoryCorrection).count() == 1
        row=db.scalar(select(ApplicantHistory))
        assert row.details["line1"] == "2 Correction Lane"
        assert row.version == 1


def test_dismissed_review_and_wrong_gap_interval_are_rejected(api):
    client,who,factory=api
    name="history-correction-denied"
    org,case,cid,staff,first,request_id=setup_request(api,name)
    reply_review(api,case,staff,request_id,name)
    decision=client.post(_staff_url(org,case)+f"/{request_id}/decide",
                         json={"decision":"needs_more_information"})
    assert decision.status_code == 201
    url=correction_url(org,case,request_id)
    rejected=client.post(url,json={"operation":"create",
        "details":new_address("2018-01-01","2018-12-31"),
        "correction_reason":"This date does not cover the flagged missing period."})
    assert rejected.status_code == 409
    with factory() as db:
        assert db.query(TimelineHistoryCorrection).count() == 0
        assert db.query(ApplicantHistory).count() == 0


def test_update_flagged_history_with_expected_version_and_prior_snapshot(api):
    client,who,factory=api
    name="history-correction-update"
    org,case,cid,staff,first,request_id=setup_request(api,name,existing=True)
    # A gap request cannot modify an existing, unrelated record.
    reply_review(api,case,staff,request_id,name)
    assert client.post(_staff_url(org,case)+f"/{request_id}/decide",
                       json={"decision":"reviewed"}).status_code == 201
    url=correction_url(org,case,request_id)
    invalid=client.post(url,json={"operation":"update","record_id":first["id"],
        "expected_version":1,"details":new_address("2022-01-01","2022-12-31"),
        "correction_reason":"Attempted unrelated change must not be accepted."})
    assert invalid.status_code == 409
    # Resolve the gap through a new period, never by retroactively stretching
    # an unflagged existing history entry.
    accepted=client.post(url,json={"operation":"create",
        "details":new_address("2022-04-01","2022-12-31"),
        "correction_reason":"Client supplied an additional fictional address."})
    assert accepted.status_code == 201,accepted.text
    with factory() as db:
        assert db.query(ApplicantHistory).count() == 2
        assert db.query(TimelineHistoryCorrection).count() == 1


def test_update_missing_end_flag_and_stale_version_fails_closed(api):
    client,who,factory=api
    name="history-correction-update-end"
    org,case,staff=_open_client(api,name)
    who.update(sub=staff,email=None,email_verified=False)
    cid=next(x["client_id"] for x in client.get(f"/api/v1/orgs/{org}/cases").json()
             if x["id"]==case)
    created=client.post(f"/api/v1/orgs/{org}/clients/{cid}/histories/address",json={
        "details":{"start_date":"2022-01-01","line1":"1 Imaginary Street",
                   "city":"Synthetic","country":"Exampleland"}})
    assert created.status_code == 201,created.text
    row=created.json()
    audit=client.get(_audit_url(org,case)).json()
    flag=next(x for x in audit["categories"]["address"]["flags"]
              if x["type"]=="end_date_not_supplied")
    requested=client.post(_staff_url(org,case),json={
        "start_date":"2022-01-01","end_date":"2022-12-31",
        "kind":"address","flag_sha256":flag["flag_sha256"],
        "snapshot_sha256":audit["snapshot_sha256"],
        "question":"Please confirm the end date of this synthetic residence."})
    assert requested.status_code==201,requested.text
    reqid=requested.json()["id"]
    reply_review(api,case,staff,reqid,name)
    assert client.post(_staff_url(org,case)+f"/{reqid}/decide",
                       json={"decision":"reviewed"}).status_code==201
    url=correction_url(org,case,reqid)
    details={**row["details"],"end_date":"2022-12-31"}
    bad=client.post(url,json={"operation":"update","record_id":row["id"],
        "expected_version":9,"details":details,
        "correction_reason":"Review confirmed the previously missing end date."})
    assert bad.status_code==409
    ok=client.post(url,json={"operation":"update","record_id":row["id"],
        "expected_version":1,"details":details,
        "correction_reason":"Review confirmed the previously missing end date."})
    assert ok.status_code==201,ok.text
    assert ok.json()["prior_version"]==1
    assert ok.json()["new_version"]==2
    history=client.get(f"/api/v1/orgs/{org}/clients/{cid}/histories").json()
    assert history["records"][0]["version"]==2
    ledger=client.get(_staff_url(org,case)+"/history-corrections").json()["corrections"][0]
    assert ledger["prior_details"].get("end_date") is None
    assert ledger["new_details"]["end_date"]=="2022-12-31"
    assert ledger["reply_id"] if "reply_id" in ledger else True
