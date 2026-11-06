"""IRCC source registry must never claim an unvalidated official application."""
from datetime import date
from uuid import UUID

from app.ircc_registry import REGISTRY, source_metadata
from app.models import CaseFact
from tests.test_api import new_org, new_client


def setup_case(api, slug='registry-study'):
    client, who, factory = api
    org = new_org(client, slug)
    cid = new_client(client, org)
    r = client.post(f'/api/v1/orgs/{org}/cases', json={
        'client_id': cid, 'application_type': 'study_permit', 'title': 'Synthetic study permit'})
    assert r.status_code == 201, r.text
    return org, r.json()['id']


def test_catalog_matches_official_page_observations_not_pdf_support(api):
    client, _, _ = api
    org, case = setup_case(api)
    r=client.get(f'/api/v1/orgs/{org}/ircc/forms')
    assert r.status_code == 200
    records={x['code']: x for x in r.json()}
    assert set(records)=={'IMM1294','IMM5709'}
    assert records['IMM1294']['filing_context']=='outside_canada'
    assert records['IMM5709']['filing_context']=='inside_canada'
    assert all(x['ircc_source_url'].startswith('https://www.canada.ca/') for x in records.values())
    assert all(x['mapping_status']=='internal_preview_only' for x in records.values())
    assert all(not x['official_pdf_generation_supported'] for x in records.values())


def test_preview_only_uses_human_verified_canonical_facts(api):
    client, _, _ = api
    org, case=setup_case(api)
    base=f'/api/v1/orgs/{org}'
    created=client.post(f'{base}/cases/{case}/facts',json={'field_path':'identity.given_name','value':'Synthetic'})
    assert created.status_code == 201, created.text
    endpoint=f'{base}/ircc/cases/{case}/forms/IMM1294/preview?filing_context=outside_canada'
    first=client.get(endpoint)
    assert first.status_code == 200
    fields={f['canonical_path']: f for f in first.json()['fields']}
    assert fields['identity.given_name']['status']=='missing'
    assert fields['identity.given_name']['value'] is None
    reviewed=client.post(f'{base}/cases/{case}/facts/{created.json()["id"]}/review',json={'status':'verified'})
    assert reviewed.status_code == 200
    response=client.get(endpoint).json()
    fields={f['canonical_path']: f for f in response['fields']}
    assert fields['identity.given_name']['value']=='Synthetic'
    assert created.json()['id'] in fields['identity.given_name']['fact_ids']
    assert response['release_status']=='blocked_no_validated_ircc_pdf_adapter'
    assert response['review_required'] is True


def test_context_and_tenant_boundaries_block_wrong_form(api):
    client,who,_=api
    org,case=setup_case(api)
    url=f'/api/v1/orgs/{org}/ircc/cases/{case}/forms/IMM1294/preview'
    assert client.get(url+'?filing_context=inside_canada').status_code==409
    assert client.get(url+'?filing_context=outside_canada').status_code==200
    assert client.get(url).status_code==422
    assert client.get(url.replace('IMM1294','IMM9999')+'?filing_context=outside_canada').status_code==404
    who['sub']='unrelated-person'
    assert client.get(url+'?filing_context=outside_canada').status_code==404
    assert client.get(f'/api/v1/orgs/{org}/ircc/forms').status_code==404


def test_review_age_is_reported_but_never_claims_current_validity():
    src=REGISTRY['IMM1294']
    old=source_metadata(src, today=date(2027,1,1))
    assert old['source_recheck_required'] is True
    assert old['official_pdf_generation_supported'] is False
    fresh=source_metadata(src, today=date(2026,11,5))
    assert fresh['source_recheck_required'] is False
    assert 'observed on official IRCC page' in fresh['observed_revision']


def test_conflicting_verified_facts_stay_ambiguous(api):
    client, who, factory = api
    org, case = setup_case(api)
    org_id, case_id = UUID(org), UUID(case)
    with factory() as db:
        db.add_all([
            CaseFact(org_id=org_id,case_id=case_id,field_path='identity.given_name',
                     value='Test A',review_status='verified',created_by_sub='synthetic-staff',reviewed_by_sub='synthetic-staff'),
            CaseFact(org_id=org_id,case_id=case_id,field_path='identity.given_name',
                     value='Test B',review_status='verified',created_by_sub='synthetic-staff',reviewed_by_sub='synthetic-staff'),
        ])
        db.commit()
    endpoint=f'/api/v1/orgs/{org}/ircc/cases/{case}/forms/IMM1294/preview?filing_context=outside_canada'
    r=client.get(endpoint)
    assert r.status_code == 200, r.text
    field=next(f for f in r.json()['fields'] if f['canonical_path']=='identity.given_name')
    assert field['status']=='ambiguous'
    assert field['value'] is None
