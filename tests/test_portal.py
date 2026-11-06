"""Security regression suite for case-scoped client portal (synthetic data only)."""
from datetime import timedelta, timezone, datetime
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import select

from app.models import Membership
from app.portal_models import PortalGrant, PortalInvitation
from app.settings import get_settings


def case_with_email(api, name='sample', email='sample.person@example.test'):
    client, who, factory = api
    who.update(sub=f'{name}-staff', email=f'{name}-staff@example.test', email_verified=True)
    org = client.post('/api/v1/orgs', json={'name': f'Synthetic {name}', 'slug': f'{name}-firm'}).json()['id']
    c = client.post(f'/api/v1/orgs/{org}/clients', json={
        'first_name': 'Fictional', 'last_name': 'Person', 'email': email})
    assert c.status_code == 201, c.text
    matter = client.post(f'/api/v1/orgs/{org}/cases', json={
        'client_id': c.json()['id'], 'application_type': 'study_permit', 'title': f'{name} case'})
    assert matter.status_code == 201, matter.text
    return org, matter.json()['id']


def invite(client, org, case):
    response = client.post(f'/api/v1/orgs/{org}/cases/{case}/portal/invitations')
    assert response.status_code == 201, response.text
    return response.json()


def claim(client, who, token, sub='synthetic-client', email='sample.person@example.test', verified=True):
    who.update(sub=sub, email=email, email_verified=verified)
    return client.post('/api/v1/client/invitations/accept', json={'token': token})


def test_bound_invite_and_one_use_token(api):
    client, who, factory = api
    org, case = case_with_email(api)
    invitation = invite(client, org, case)
    assert len(invitation['invite_token']) > 50
    assert 'sample.person' not in str(invitation)
    with factory() as db:
        row = db.scalar(select(PortalInvitation).where(PortalInvitation.id == UUID(invitation['invitation_id'])))
        assert invitation['invite_token'] != row.token_hash
    assert claim(client, who, invitation['invite_token'], email='wrong@example.test').status_code == 404
    assert claim(client, who, invitation['invite_token'], verified=False).status_code == 403
    response = claim(client, who, invitation['invite_token'])
    assert response.status_code == 200, response.text
    assert response.json()['case_id'] == case
    assert claim(client, who, invitation['invite_token']).status_code == 404
    cases = client.get('/api/v1/client/cases')
    assert cases.status_code == 200 and len(cases.json()) == 1
    assert cases.json()[0]['title'] == 'sample case'
    # Client principal is never a firm member: existing staff APIs remain forbidden.
    assert client.get(f'/api/v1/orgs/{org}/cases').status_code == 404
    assert client.get(f'/api/v1/orgs/{org}/clients').status_code == 404
    assert client.get(f'/api/v1/orgs/{org}/audit').status_code == 404


def test_invitation_expiry_revocation_and_wrong_case(api):
    client, who, factory = api
    org, case = case_with_email(api, 'expiry')
    token = invite(client, org, case)
    with factory() as db:
        invitation = db.get(PortalInvitation, UUID(token['invitation_id']))
        invitation.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert claim(client, who, token['invite_token'], email='sample.person@example.test').status_code == 404
    who.update(sub='expiry-staff', email='expiry-staff@example.test', email_verified=True)
    new_invite = invite(client, org, case)
    path = f'/api/v1/orgs/{org}/cases/{case}/portal/invitations/{new_invite["invitation_id"]}/revoke'
    assert client.post(path).status_code == 200
    assert claim(client, who, new_invite['invite_token']).status_code == 404


def test_document_request_client_upload_quarantine_and_revocation(api, monkeypatch, tmp_path):
    client, who, factory = api
    monkeypatch.setattr(get_settings(), 'uploads_enabled', True)
    monkeypatch.setattr(get_settings(), 'document_encryption_key', Fernet.generate_key().decode())
    monkeypatch.setattr(get_settings(), 'document_storage_root', str(tmp_path))
    org, case = case_with_email(api, 'upload')
    staff_sub = who['sub']
    base = f'/api/v1/orgs/{org}/cases/{case}/portal'
    req = client.post(base+'/requests', json={
        'title':'Synthetic employment letter','document_type':'employment_letter',
        'instructions':'Fictional document only'})
    assert req.status_code == 201, req.text
    request_id = req.json()['id']
    inv = invite(client, org, case)
    assert claim(client, who, inv['invite_token'], sub='portal-client', email='sample.person@example.test').status_code == 200
    requested = client.get(f'/api/v1/client/cases/{case}/requests')
    assert requested.status_code == 200 and len(requested.json()) == 1
    other = client.get('/api/v1/client/cases/00000000-0000-0000-0000-000000000001/requests')
    assert other.status_code == 404
    prefix=f'/api/v1/client/cases/{case}/requests/{request_id}/upload'
    bad = client.post(prefix, files={'file':('fake.pdf',b'fake','application/pdf')})
    assert bad.status_code == 415
    upload = client.post(prefix, files={'file':('demo.txt',b'Fictional example only','text/plain')})
    assert upload.status_code == 201, upload.text
    assert upload.json()['scan_status'] == 'quarantined'
    assert client.post(prefix, files={'file':('duplicate.txt',b'Sample','text/plain')}).status_code == 409
    # Client cannot download through the staff API.
    assert client.get(f'/api/v1/orgs/{org}/cases/{case}/documents').status_code == 404
    who.update(sub=staff_sub,email='upload-staff@example.test',email_verified=True)
    submissions = client.get(base+'/submissions').json()
    assert len(submissions) == 1
    docid = submissions[0]['document_id']
    staff_url=f'/api/v1/orgs/{org}/cases/{case}'
    assert client.get(f'{staff_url}/documents/{docid}/download').status_code == 423
    assert client.post(f'{staff_url}/documents/{docid}/extract').status_code == 423
    grants=client.get(base+'/grants')
    assert grants.status_code == 200 and len(grants.json()) == 1
    assert client.post(base+'/grants/'+grants.json()[0]['id']+'/revoke').status_code == 200
    who.update(sub='portal-client',email='sample.person@example.test',email_verified=True)
    assert client.get(f'/api/v1/client/cases/{case}/requests').status_code == 404
    assert client.get('/api/v1/client/cases').json() == []
    assert client.post(prefix, files={'file':('again.txt',b'Sample','text/plain')}).status_code == 404


def test_cross_firm_and_role_restrictions(api):
    client, who, factory = api
    org, case = case_with_email(api, 'first')
    org2, case2 = case_with_email(api, 'second')
    # User from second firm cannot create requests or invitations in first firm.
    assert client.post(f'/api/v1/orgs/{org}/cases/{case}/portal/invitations').status_code == 404
    assert client.post(f'/api/v1/orgs/{org}/cases/{case}/portal/requests',
                       json={'title':'Cross firm request','document_type':'passport'}).status_code == 404
    who.update(sub='second-viewer',email='viewer@example.test',email_verified=True)
    with factory() as db:
        db.add(Membership(org_id=UUID(org2),subject='second-viewer',role='viewer',is_active=True))
        db.commit()
    assert client.post(f'/api/v1/orgs/{org2}/cases/{case2}/portal/invitations').status_code == 403
    assert client.post(f'/api/v1/orgs/{org2}/cases/{case2}/portal/requests',
                       json={'title':'No privilege','document_type':'passport'}).status_code == 403
