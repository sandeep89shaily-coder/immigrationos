"""Adversarial client-portal RLS/API smoke test on real PostgreSQL app role.

Synthetic data only; runs in CI after migration with DATABASE_URL=limited app role.
"""
from uuid import uuid4
from fastapi.testclient import TestClient
from app.auth import Principal, get_principal
from app.main import app

person = {'sub': 'staff', 'email': None, 'verified': False}


def principal():
    return Principal(sub=person['sub'], email=person['email'], email_verified=person['verified'])


app.dependency_overrides[get_principal] = principal
try:
    with TestClient(app) as api:
        case_ids=[]
        for i in range(2):
            person.update(sub=f'portal-staff-{i}-{uuid4()}', email=None, verified=False)
            r=api.post('/api/v1/orgs', json={'name':'Synthetic Practice', 'slug':'portal-smoke-'+uuid4().hex})
            assert r.status_code==201, r.text
            org=r.json()['id']
            r=api.post(f'/api/v1/orgs/{org}/clients', json={
                'first_name':'Fictional','last_name':'Applicant','email':f'person{i}@example.test'})
            assert r.status_code==201, r.text
            r=api.post(f'/api/v1/orgs/{org}/cases', json={
                'client_id':r.json()['id'],'application_type':'study_permit','title':'Synthetic permit'})
            assert r.status_code==201, r.text
            case=r.json()['id']
            r=api.post(f'/api/v1/orgs/{org}/cases/{case}/portal/requests', json={
                'title':'Synthetic passport','document_type':'passport'})
            assert r.status_code==201, r.text
            request_id=r.json()['id']
            r=api.post(f'/api/v1/orgs/{org}/cases/{case}/portal/invitations')
            assert r.status_code==201, r.text
            case_ids.append((org,case,request_id,r.json()['invite_token']))
        # A client principal may only accept the invitation bound to verified email.
        person.update(sub='portal-recipient-'+uuid4().hex,email='person0@example.test',verified=True)
        r=api.post('/api/v1/client/invitations/accept',json={'token':case_ids[1][3]})
        assert r.status_code==404, r.text
        r=api.post('/api/v1/client/invitations/accept',json={'token':case_ids[0][3]})
        assert r.status_code==200, r.text
        assert api.post('/api/v1/client/invitations/accept',json={'token':case_ids[0][3]}).status_code==404
        r=api.get('/api/v1/client/cases')
        assert r.status_code==200 and [c['id'] for c in r.json()]==[case_ids[0][1]],r.text
        r=api.get('/api/v1/client/cases/'+case_ids[0][1]+'/requests')
        assert r.status_code==200 and len(r.json())==1,r.text
        assert api.get('/api/v1/client/cases/'+case_ids[1][1]+'/requests').status_code==404
        assert api.get(f'/api/v1/orgs/{case_ids[0][0]}/clients').status_code==404
finally:
    app.dependency_overrides.clear()
print('PASS: PostgreSQL verified-email invitation, case-scoped grant and cross-firm denial')
