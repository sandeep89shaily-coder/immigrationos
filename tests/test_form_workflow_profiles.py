"""IMM 5476 workflow profiles must follow the published sections and signatures."""
import pytest

from app.form_workflow_profiles import imm5476_workflow, OPERATIONS
from tests.test_api import new_org


@pytest.mark.parametrize(("operation", "expected"), [
    ("appoint", ["A", "B", "E"]),
    ("update_contact", ["A", "B", "E"]),
    ("cancel", ["A", "C", "E"]),
    ("replace", ["A", "B", "C", "E"]),
    ("withdraw", ["A", "D", "E"]),
])
def test_rep_workflow_sections_follow_current_ircc_instructions(operation, expected):
    result = imm5476_workflow(operation, "portal_or_secure_account")
    assert [s["code"] for s in result["sections"]] == expected
    assert result["revision"] == "11-2025"
    assert result["reviewed_information_only"] is True
    assert result["official_pdf_autofill_supported"] is False
    assert result["official_pdf_validation_verified"] is False
    assert result["submission_supported"] is False


def test_paper_and_online_signature_guidance_different():
    online = imm5476_workflow("appoint", "portal_or_secure_account")
    outside = imm5476_workflow("appoint", "outside_portal")
    assert "electronic signature" in " ".join(online["notes"])
    assert "handwritten signatures" in " ".join(outside["notes"])
    assert online["applicant_signature_review_required"] is True
    assert outside["representative_identity_required"] is True


def test_dependent_and_spouse_authorization_is_not_automatically_implied():
    result = imm5476_workflow("replace", "outside_portal")
    notes = " ".join(result["notes"])
    assert "18 or older" in notes
    assert "Spouses/common-law partners" in notes
    assert result["field_mapping_available"] is False


def test_invalid_operation_and_channel_denied():
    with pytest.raises(ValueError):
        imm5476_workflow("fake", "portal_or_secure_account")
    with pytest.raises(ValueError):
        imm5476_workflow("appoint", "automatic_submission")


def test_imm5476_workflow_is_tenant_scoped(api):
    client, who, _ = api
    org = new_org(client, "representative-guidance")
    endpoint = (f"/api/v1/orgs/{org}/ircc/forms/IMM5476/workflow?"
                "operation=appoint&submission_channel=portal_or_secure_account")
    result = client.get(endpoint)
    assert result.status_code == 200, result.text
    assert result.json()["operation"] == "appoint"
    assert result.json()["revision"] == "11-2025"
    who["sub"] = "outsider"
    assert client.get(endpoint).status_code == 404
    who["sub"] = "test-user-a"
    assert client.get(endpoint.replace("operation=appoint","operation=fake")).status_code == 422
