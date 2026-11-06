"""Published form-coverage counts cannot be inflated by discovery."""
from tests.test_api import new_org


def test_form_coverage_is_truthful_and_tenant_isolated(api):
    client, who, _ = api
    org = new_org(client, "truthful-form-coverage")
    r = client.get(f"/api/v1/orgs/{org}/ircc/coverage")
    assert r.status_code == 200, r.text
    value = r.json()
    assert value["official_pdf_autofill_supported"] == 0
    assert value["official_pdf_validation_verified"] == 0
    assert value["official_submission_integrations"] == 0
    assert value["indexed_contexts_with_internal_preview"] == 2
    assert len(value["forms"]) == 2
    assert all(not record["official_pdf_autofill"] for record in value["forms"])
    assert value["synthetic_static_acroform_adapter"] is True
    who["sub"] = "unrelated-subject"
    assert client.get(f"/api/v1/orgs/{org}/ircc/coverage").status_code == 404
