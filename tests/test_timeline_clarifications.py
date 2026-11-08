"""End-to-end timeline clarification from real flag through portal and review."""
from uuid import UUID
from sqlalchemy import select

from app.applicant_history_models import ApplicantHistory
from app.timeline_clarification_models import (TimelineClarification,
    TimelineClarificationReply, TimelineClarificationDecision)
from tests.test_study_intake import _open_client
from tests.test_api import new_org, new_client


def _staff_url(org, case):
    return f"/api/v1/orgs/{org}/cases/{case}/timeline-clarifications"


def _client_url(case):
    return f"/api/v1/client/cases/{case}/timeline-clarifications"


def _audit_url(org, case):
    return f"/api/v1/orgs/{org}/cases/{case}/history-timeline-audit?start_date=2022-01-01&end_date=2022-12-31"


def test_request_reply_and_review_do_not_mutate_master_history(api):
    client, who, factory = api
    org, case, staff = _open_client(api, "timeline-clarify-flow")
    who.update(sub=staff, email=None, email_verified=False)
    cases=client.get(f"/api/v1/orgs/{org}/cases").json()
    cid=next(x["client_id"] for x in cases if x["id"]==case)
    original=client.post(f"/api/v1/orgs/{org}/clients/{cid}/histories/address",json={
        "details":{"start_date":"2022-01-01","end_date":"2022-03-31",
                   "line1":"1 Fake Road","city":"Fake City","country":"Exampleland"}})
    assert original.status_code==201,original.text
    audit=client.get(_audit_url(org,case))
    assert audit.status_code==200,audit.text
    data=audit.json()
    flag=next(x for x in data["categories"]["address"]["flags"]
              if x["type"]=="uncovered_period_for_review")
    url=_staff_url(org,case)
    payload={"start_date":"2022-01-01","end_date":"2022-12-31",
             "kind":"address","flag_sha256":flag["flag_sha256"],
             "snapshot_sha256":data["snapshot_sha256"],
             "question":"Please explain your residential history for the uncovered period."}
    assert client.post(url,json={**payload,"flag_sha256":"f"*64}).status_code==409
    created=client.post(url,json=payload)
    assert created.status_code==201,created.text
    reqid=created.json()["id"]
    assert client.post(url,json=payload).status_code==409
    assert client.post(url+f"/{reqid}/decide",json={"decision":"reviewed"}).status_code==409
    who.update(sub="timeline-clarify-flow-client",
               email="sample.person@example.test",email_verified=True)
    portal=_client_url(case)
    received=client.get(portal)
    assert received.status_code==200,received.text
    assert received.json()["requests"][0]["question"]==payload["question"]
    answer=client.post(portal+f"/{reqid}/reply",json={
        "answer":"I was temporarily staying with my fictional relatives."})
    assert answer.status_code==201,answer.text
    assert answer.json()["master_history_updated"] is False
    assert client.post(portal+f"/{reqid}/reply",json={
        "answer":"Another explanation that must be rejected"}).status_code==409
    who.update(sub=staff,email=None,email_verified=False)
    pending=client.get(url).json()["requests"][0]
    assert pending["status"]=="awaiting_staff"
    assert "fictional relatives" in pending["reply"]
    accepted=client.post(url+f"/{reqid}/decide",json={"decision":"reviewed"})
    assert accepted.status_code==201,accepted.text
    assert accepted.json()["verified_evidence"] is False
    assert client.post(url+f"/{reqid}/decide",json={
        "decision":"needs_more_information"}).status_code==409
    with factory() as db:
        assert db.query(ApplicantHistory).count()==1
        assert db.query(TimelineClarification).count()==1
        assert db.query(TimelineClarificationReply).count()==1
        assert db.query(TimelineClarificationDecision).count()==1
        row=db.scalar(select(ApplicantHistory))
        assert row.details["end_date"]=="2022-03-31"


def test_stale_snapshot_rejected_and_client_scope(api):
    client,who,factory=api
    org,case,staff=_open_client(api,"timeline-clarify-stale")
    who.update(sub=staff,email=None,email_verified=False)
    audit=client.get(_audit_url(org,case)).json()
    flag=audit["categories"]["address"]["flags"][0]
    url=_staff_url(org,case)
    payload={"start_date":"2022-01-01","end_date":"2022-12-31",
             "kind":"address","flag_sha256":flag["flag_sha256"],
             "snapshot_sha256":audit["snapshot_sha256"],
             "question":"Please describe where you lived during this date range."}
    cid=next(x["client_id"] for x in client.get(f"/api/v1/orgs/{org}/cases").json()
             if x["id"]==case)
    change=client.post(f"/api/v1/orgs/{org}/clients/{cid}/histories/address",json={
        "details":{"start_date":"2022-01-01","end_date":"2022-12-31",
                   "line1":"Imaginary Place","city":"Example","country":"Fictionland"}})
    assert change.status_code==201
    assert client.post(url,json=payload).status_code==409
    who.update(sub="timeline-clarify-stale-client",
               email="sample.person@example.test",email_verified=True)
    assert client.get(_client_url(case)).status_code==200
    assert client.get(url).status_code==404
    who.update(sub="unrelated-person",email=None,email_verified=False)
    assert client.get(url).status_code==404
    assert client.get(_client_url(case)).status_code in (403,404)
