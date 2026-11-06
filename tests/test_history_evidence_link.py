from tests.test_applicant_histories import context
from tests.test_application_package import add_pdf


def test_history_link_remains_pending(api):
    client, _, _ = api
    org, case, _, root = context(api, 'history-link')
    row = client.post(root + '/travel', json={'details': {'start_date': '2024-01-01', 'purpose': 'Test trip', 'destination_country': 'Fictionland'}}).json()
    doc = add_pdf(api, org, case)
    path = f'/api/v1/orgs/{org}/cases/{case}/histories/{row["id"]}/fields/purpose/evidence'
    result = client.post(path, json={'document_id': doc})
    assert result.status_code == 201, result.text
    assert result.json()['review_status'] == 'pending'
