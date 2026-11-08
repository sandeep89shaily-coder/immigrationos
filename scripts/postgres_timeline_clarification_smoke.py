"""Restricted PostgreSQL timeline clarification API and portal RLS smoke."""
from uuid import uuid4

from fastapi.testclient import TestClient
from app.auth import Principal, get_principal
from app.main import app

who={"sub":"timeline-owner-"+uuid4().hex,"email":None,"verified":False}

def principal():
    return Principal(sub=who["sub"], email=who["email"],
                     email_verified=who["verified"])

app.dependency_overrides[get_principal]=principal
try:
    with TestClient(app) as api:
        staff=who["sub"]
        org=api.post("/api/v1/orgs",json={
            "name":"Fictional Timeline Firm","slug":"timeline-smoke-"+uuid4().hex})
        assert org.status_code==201,org.text
        org_id=org.json()["id"]
        person=api.post(f"/api/v1/orgs/{org_id}/clients",json={
            "first_name":"Sample","last_name":"Applicant",
            "email":"timeline-"+uuid4().hex+"@example.test"})
        assert person.status_code==201,person.text
        case=api.post(f"/api/v1/orgs/{org_id}/cases",json={
            "client_id":person.json()["id"],"application_type":"study_permit",
            "title":"Synthetic chronology matter"})
        assert case.status_code==201,case.text
        case_id=case.json()["id"]
        url=f"/api/v1/orgs/{org_id}/cases/{case_id}/timeline-clarifications"
        audit=api.get(f"/api/v1/orgs/{org_id}/cases/{case_id}/history-timeline-audit"+
                      "?start_date=2022-01-01&end_date=2022-12-31")
        assert audit.status_code==200,audit.text
        data=audit.json()
        flag=data["categories"]["address"]["flags"][0]
        request=api.post(url,json={
            "start_date":"2022-01-01","end_date":"2022-12-31",
            "kind":"address","flag_sha256":flag["flag_sha256"],
            "snapshot_sha256":data["snapshot_sha256"],
            "question":"Please explain your address history during this uncovered period."})
        assert request.status_code==201,request.text
        reqid=request.json()["id"]
        invite=api.post(f"/api/v1/orgs/{org_id}/cases/{case_id}/portal/invitations")
        assert invite.status_code==201,invite.text
        who.update(sub="timeline-client-"+uuid4().hex,
                   email=person.json()["email"],verified=True)
        claimed=api.post("/api/v1/client/invitations/accept",json={
            "token":invite.json()["invite_token"]})
        assert claimed.status_code==200,claimed.text
        client_url=f"/api/v1/client/cases/{case_id}/timeline-clarifications"
        listed=api.get(client_url)
        assert listed.status_code==200,listed.text
        assert listed.json()["requests"][0]["status"]=="awaiting_client"
        replied=api.post(client_url+f"/{reqid}/reply",json={
            "answer":"I was staying at a fictional temporary residence during that period."})
        assert replied.status_code==201,replied.text
        assert replied.json()["verified_evidence"] is False
        who.update(sub=staff,email=None,verified=False)
        reviewed=api.post(url+f"/{reqid}/decide",json={"decision":"reviewed"})
        assert reviewed.status_code==201,reviewed.text
        assert reviewed.json()["master_history_updated"] is False
        who.update(sub="outsider-"+uuid4().hex,email=None,verified=False)
        assert api.get(url).status_code==404
        assert api.get(client_url).status_code in (403,404)
finally:
    app.dependency_overrides.clear()
print("PASS: restricted PostgreSQL timeline request, portal reply and human decision")
