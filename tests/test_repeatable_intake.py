"""Client-to-consultant repeatable intake: immutable, tenant-scoped, unverified."""
from uuid import UUID

from app.applicant_models import FamilyMember
from app.applicant_history_models import ApplicantHistory
from app.repeatable_intake_models import ClientRepeatableProposal, ClientRepeatableDecision
from tests.test_study_intake import _open_client


def _urls(org, case):
    return (f"/api/v1/client/cases/{case}/repeatables",
            f"/api/v1/orgs/{org}/cases/{case}/repeatables")


def _send(client, url, kind, details, *, version=None, acknowledged=True):
    info = client.get(url).json()
    return client.post(url, json={
        "kind": kind, "details": details,
        "template_version": version or info["template_version"],
        "acknowledged_notice": acknowledged})


def test_family_proposal_is_immutable_until_consultant_accepts(api):
    client, who, factory = api
    org, case, staff = _open_client(api, "repeatable-family")
    portal, backoffice = _urls(org, case)
    details = {"relationship": "child", "given_name": "Example",
               "family_name": "Child", "date_of_birth": "2011-02-03"}
    saved = _send(client, portal, "family", details)
    assert saved.status_code == 201, saved.text
    proposal_id = saved.json()["id"]
    assert saved.json()["verified_evidence"] is False
    assert saved.json()["master_profile_updated"] is False
    assert _send(client, portal, "family", details).status_code == 409
    assert len(client.get(portal).json()["proposals"]) == 1
    with factory() as db:
        assert db.query(FamilyMember).count() == 0
        row = db.query(ClientRepeatableProposal).one()
        assert row.kind == "family"
        assert len(row.content_sha256) == 64

    who.update(sub=staff, email=None, email_verified=False)
    listing = client.get(backoffice)
    assert listing.status_code == 200, listing.text
    assert listing.json()["pending_count"] == 1
    accepted = client.post(backoffice + f"/{proposal_id}/decide",
                           json={"decision": "accept"})
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["verified_evidence"] is False
    assert accepted.json()["master_claim_created"] is True
    with factory() as db:
        row = db.query(FamilyMember).one()
        assert row.given_name == "Example"
        assert row.version == 1
        assert db.query(ClientRepeatableDecision).one().created_record_id == row.id
    assert client.post(backoffice + f"/{proposal_id}/decide",
                       json={"decision": "accept"}).status_code == 409


def test_histories_validate_periods_and_staff_dismiss_is_not_import(api):
    client, who, factory = api
    org, case, staff = _open_client(api, "repeatable-histories")
    portal, office = _urls(org, case)
    invalid = _send(client, portal, "employment", {
        "start_date": "2025-01-01", "end_date": "2024-01-01",
        "employer": "Synthetic", "position": "Tester", "country": "Fictionland",
        "employment_status": "employed"})
    assert invalid.status_code == 422
    assert _send(client, portal, "other", {"name": "Unknown", "value": "bad"}).status_code == 422
    assert _send(client, portal, "address", {
        "start_date": "2024-01-01", "line1": "1 Demo Lane",
        "city": "Fiction City", "country": "Fictionland"},
        acknowledged=False).status_code == 422
    created = _send(client, portal, "address", {
        "start_date": "2024-01-01", "line1": "1 Demo Lane",
        "city": "Fiction City", "country": "Fictionland"})
    assert created.status_code == 201, created.text
    who.update(sub=staff, email=None, email_verified=False)
    dismissal = client.post(office + f"/{created.json()['id']}/decide",
                            json={"decision": "dismiss"})
    assert dismissal.status_code == 201
    with factory() as db:
        assert db.query(ApplicantHistory).count() == 0
    assert client.get(office).json()["pending_count"] == 0


def test_history_accept_and_strict_case_staff_permissions(api):
    client, who, factory = api
    org, case, staff = _open_client(api, "repeatable-history-accept")
    portal, office = _urls(org, case)
    first = _send(client, portal, "education", {
        "start_date": "2020-09-01", "end_date": "2024-06-01",
        "institution": "Imaginary University",
        "program": "Mechanical Engineering", "country": "Fictionland"})
    assert first.status_code == 201
    proposal_id = first.json()["id"]
    # Client cannot access staff review endpoints.
    assert client.get(office).status_code == 404
    assert client.post(office + f"/{proposal_id}/decide",
                       json={"decision": "accept"}).status_code == 404
    who.update(sub=staff, email=None, email_verified=False)
    accepted = client.post(office + f"/{proposal_id}/decide",
                           json={"decision": "accept"})
    assert accepted.status_code == 201, accepted.text
    with factory() as db:
        row = db.query(ApplicantHistory).one()
        assert row.details["institution"] == "Imaginary University"
        assert row.version == 1
    # Repeating exactly the same record in another proposal should be blocked
    # from silently creating duplicate master entries.
    who.update(sub="repeatable-history-accept-client",
               email="sample.person@example.test", email_verified=True)
    # Same original portal actor cannot submit identical proposal again.
    assert _send(client, portal, "education", {
        "start_date": "2020-09-01", "end_date": "2024-06-01",
        "institution": "Imaginary University", "program": "Mechanical Engineering",
        "country": "Fictionland"}).status_code == 409


def test_former_relationship_proposals_are_repeatable_and_staff_reviewed(api):
    from app.applicant_supplemental_history_models import ApplicantSupplementalHistory
    client, who, factory = api
    org, case, staff = _open_client(api, "repeatable-former-partner")
    portal, office = _urls(org, case)
    first = {
        "relationship_type":"married",
        "family_name":"Fiction", "given_name":"Former",
        "date_of_birth":"1988-06-01",
        "start_date":"2010-01-01", "end_date":"2015-01-01",
    }
    assert _send(client,portal,"previous_relationship",
                 {**first,"end_date":"2009-01-01"}).status_code==422
    assert _send(client,portal,"previous_relationship",
                 {**first,"relationship_type":"unknown"}).status_code==422
    one=_send(client,portal,"previous_relationship",first)
    assert one.status_code==201,one.text
    other=_send(client,portal,"previous_relationship",
                {**first,"family_name":"Different","start_date":"2016-01-01",
                 "end_date":"2018-01-01"})
    assert other.status_code==201,other.text
    assert _send(client,portal,"previous_relationship",first).status_code==409
    who.update(sub=staff,email=None,email_verified=False)
    assert client.get(office+"/master-records").json()["records"]==[]
    accepted=client.post(office+f"/{one.json()['id']}/decide",
                         json={"decision":"accept"})
    assert accepted.status_code==201,accepted.text
    declined=client.post(office+f"/{other.json()['id']}/decide",
                         json={"decision":"dismiss"})
    assert declined.status_code==201,declined.text
    view=client.get(office+"/master-records")
    assert view.status_code==200,view.text
    assert view.headers["cache-control"]=="no-store"
    assert len(view.json()["records"])==1
    assert view.json()["records"][0]["details"]["family_name"]=="Fiction"
    assert view.json()["verified_evidence"] is False
    with factory() as db:
        assert db.query(ApplicantSupplementalHistory).count()==1
        assert db.query(ApplicantSupplementalHistory).one().version==1


def test_previous_residence_requires_bounded_dates_and_other_status_explanation(api):
    from app.applicant_supplemental_history_models import ApplicantSupplementalHistory
    client, who, factory=api
    org, case, staff=_open_client(api,"repeatable-foreign-stays")
    portal, office=_urls(org,case)
    base={"country":"Fictionland","status":"student",
          "start_date":"2020-01-01","end_date":"2021-02-01"}
    assert _send(client,portal,"foreign_residence",
                 {**base,"end_date":"2019-12-31"}).status_code==422
    assert _send(client,portal,"foreign_residence",
                 {**base,"status":"other"}).status_code==422
    assert _send(client,portal,"foreign_residence",
                 {**base,"status_other":"out of status"}).status_code==422
    assert _send(client,portal,"foreign_residence",
                 {k:v for k,v in base.items() if k!="end_date"}).status_code==422
    good=_send(client,portal,"foreign_residence",
               {**base,"status":"other","status_other":"Synthetic status"})
    assert good.status_code==201,good.text
    who.update(sub=staff,email=None,email_verified=False)
    out=client.post(office+f"/{good.json()['id']}/decide",
                    json={"decision":"accept"})
    assert out.status_code==201,out.text
    assert out.json()["verified_evidence"] is False
    assert out.json()["master_claim_created"] is True
    assert client.post(office+f"/{good.json()['id']}/decide",
                       json={"decision":"accept"}).status_code==409
    with factory() as db:
        row=db.query(ApplicantSupplementalHistory).one()
        assert row.kind=="foreign_residence"
        assert row.details["status_other"]=="Synthetic status"
        assert row.version==1


def test_supplemental_master_readback_not_accessible_to_portal_or_other_case(api):
    client,who,factory=api
    org,case,staff=_open_client(api,"repeatable-foreign-scope")
    portal,office=_urls(org,case)
    assert client.get(office+"/master-records").status_code==404
    who.update(sub=staff,email=None,email_verified=False)
    assert client.get(office+"/master-records").status_code==200
    from uuid import uuid4
    assert client.get(f"/api/v1/orgs/{org}/cases/{uuid4()}/repeatables/master-records").status_code==404
    who.update(sub="unrelated-supplemental-principal",email=None,email_verified=False)
    assert client.get(office+"/master-records").status_code==404
