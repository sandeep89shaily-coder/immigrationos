"""Review evidence stays stale when case data changes; no approval is inferred."""
from uuid import UUID

from app.models import EvidenceReviewSnapshot, Membership
from tests.test_evidence_matrix import setup_case


def test_review_snapshot_stales_on_new_fact(api):
    client, _, factory = api
    org, case = setup_case(api, 'review-stales')
    base = f'/api/v1/orgs/{org}/cases/{case}'
    current = client.get(base+'/reviews/current?filing_context=outside_canada')
    assert current.status_code == 200, current.text
    digest = current.json()['case_sha256']
    reviewed = client.post(base+'/reviews/record', json={
        'filing_context': 'outside_canada', 'expected_sha256': digest,
        'review_note': 'Reviewed synthetic evidence against applicable instructions.',
        'reviewed_current_ircc_sources': True})
    assert reviewed.status_code == 201, reviewed.text
    assert reviewed.json()['ircc_submission_authorized'] is False
    first = client.get(base+'/reviews/history?filing_context=outside_canada')
    assert first.status_code == 200 and len(first.json()['history']) == 1
    assert first.json()['history'][0]['is_current'] is True
    created = client.post(base+'/facts',json={'field_path':'identity.given_name','value':'Synthetic'})
    assert created.status_code == 201
    updated = client.get(base+'/reviews/history?filing_context=outside_canada').json()
    assert updated['current']['case_sha256'] != digest
    assert updated['history'][0]['is_current'] is False
    blocked = client.post(base+'/reviews/record', json={
        'filing_context': 'outside_canada', 'expected_sha256': digest,
        'review_note': 'Incorrect old evidence review from before client update.',
        'reviewed_current_ircc_sources': True})
    assert blocked.status_code == 409
    refreshed = client.post(base+'/reviews/record', json={
        'filing_context':'outside_canada', 'expected_sha256':updated['current']['case_sha256'],
        'review_note': 'I checked the updated facts and confirmed official sources.',
        'reviewed_current_ircc_sources': True})
    assert refreshed.status_code == 201
    assert len(client.get(base+'/reviews/history?filing_context=outside_canada').json()['history']) == 2
    with factory() as db:
        assert db.query(EvidenceReviewSnapshot).count() == 2


def test_cannot_review_without_source_acknowledgment_or_permissions(api):
    client, who, factory = api
    org, case = setup_case(api, 'review-perms')
    base=f'/api/v1/orgs/{org}/cases/{case}/reviews'
    digest=client.get(base+'/current?filing_context=inside_canada').json()['case_sha256']
    payload={
        'filing_context':'inside_canada','expected_sha256':digest,
        'review_note':'All operational issues still require professional review.',
        'reviewed_current_ircc_sources':False}
    assert client.post(base+'/record',json=payload).status_code==422
    who['sub']='viewer'
    with factory() as db:
        db.add(Membership(org_id=UUID(org),subject='viewer',role='viewer',is_active=True));db.commit()
    assert client.get(base+'/history?filing_context=inside_canada').status_code==404
    assert client.post(base+'/record',json={**payload,'reviewed_current_ircc_sources':True}).status_code==404
    who['sub']='outsider'
    assert client.get(base+'/history?filing_context=inside_canada').status_code==404
    who['sub']='test-user-a'
    assert client.post(base+'/record',json={**payload,'reviewed_current_ircc_sources':True}).status_code==201
    assert client.get(base+'/history?filing_context=outside_canada').json()['history']==[]


def test_status_and_upload_scan_changes_change_digest(api):
    client, _, _ = api
    org, case = setup_case(api, 'review-status')
    base=f'/api/v1/orgs/{org}/cases/{case}'
    before=client.get(base+'/reviews/current?filing_context=outside_canada').json()['case_sha256']
    change=client.patch(base+'/status',json={'status':'intake','reason':'Begin a fictional intake'})
    assert change.status_code==200
    after=client.get(base+'/reviews/current?filing_context=outside_canada').json()['case_sha256']
    assert before!=after
    closed=client.patch(base+'/status',json={'status':'closed','reason':'Synthetic case completed'})
    assert closed.status_code==200
    resp=client.post(base+'/reviews/record',json={
        'filing_context':'outside_canada', 'expected_sha256':after,
        'review_note':'Previous review should not apply after case closure.',
        'reviewed_current_ircc_sources':True})
    assert resp.status_code==409
