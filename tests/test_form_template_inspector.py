"""Untrusted blank template triage — synthetic fixture only."""
from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject
from reportlab.pdfgen.canvas import Canvas

from app.form_template_inspector import TemplateInspectionError, inspect_pdf_template
from tests.test_api import new_org


def create_fixture(*, fields=True):
    buffer = BytesIO()
    page = Canvas(buffer, pagesize=(450, 400))
    page.drawString(40, 360, "SYNTHETIC DEVELOPMENT TEMPLATE — NOT AN IRCC FORM")
    if fields:
        page.acroForm.textfield(name="applicant_given_name", x=35, y=300,
                                width=190, height=22, forceBorder=True)
        page.acroForm.textfield(name="applicant_family_name", x=35, y=260,
                                width=190, height=22, forceBorder=True)
    page.save()
    return buffer.getvalue()


def write_modified_pdf(pdf, mutate):
    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(pdf)))
    mutate(writer)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def add_xfa(writer):
    acro = writer._root_object["/AcroForm"].get_object()
    acro[NameObject("/XFA")] = TextStringObject("synthetic-xfa-marker")


def add_document_action(writer):
    writer._root_object[NameObject("/OpenAction")] = TextStringObject("synthetic-action-marker")


def add_populated_value(writer):
    writer.update_page_form_field_values(None, {"applicant_given_name": "Jane"}, auto_regenerate=False)


def test_blank_static_fixture_is_candidate_but_never_approved():
    result = inspect_pdf_template(create_fixture())
    assert result["classification"] == "static_acroform_candidate"
    assert result["candidate_for_static_adapter"] is True
    assert result["field_count"] == 2
    assert result["field_type_counts"] == {"text": 2}
    assert result["field_names"] == ["applicant_family_name", "applicant_given_name"]
    assert result["requires_barcode_and_signature_review"] is True
    assert result["official_pdf_autofill_supported"] is False
    assert result["independently_validated"] is False
    assert result["submission_supported"] is False


def test_xfa_marker_is_never_treated_as_static():
    raw = write_modified_pdf(create_fixture(), add_xfa)
    report = inspect_pdf_template(raw)
    assert report["classification"] == "xfa_or_hybrid_requires_adobe_workflow"
    assert "xfa_present" in report["indicators"]
    assert report["candidate_for_static_adapter"] is False


def test_active_content_is_blocked_from_static_classification():
    raw = write_modified_pdf(create_fixture(), add_document_action)
    report = inspect_pdf_template(raw)
    assert report["classification"] == "active_content_requires_manual_review"
    assert "document_actions" in report["indicators"]


def test_populated_pdf_is_rejected_for_blank_template_inspection():
    raw = write_modified_pdf(create_fixture(), add_populated_value)
    result = inspect_pdf_template(raw)
    assert result["classification"] == "nonblank_template_rejected"
    assert "populated_fields_present" in result["indicators"]
    assert result["candidate_for_static_adapter"] is False


def test_pdf_without_fields_cannot_be_autofilled():
    report = inspect_pdf_template(create_fixture(fields=False))
    assert report["classification"] == "nonfillable_pdf_requires_manual_review"
    assert report["field_count"] == 0


@pytest.mark.parametrize("raw", [b"", b"not a PDF", b"%PDF-malformed", b"%PDF-" + b"a"*12_582_912])
def test_invalid_or_oversized_templates_fail_safely(raw):
    with pytest.raises(TemplateInspectionError):
        inspect_pdf_template(raw)


def test_inspection_endpoint_is_firm_authenticated_and_never_stores_pdf(api):
    client, identity, _ = api
    org = new_org(client, "form-template-triage")
    url = f"/api/v1/orgs/{org}/ircc/inspect-template"
    response = client.post(url, data={"form_code": "IMM5476"}, files={
        "file": ("blank-representative-test.pdf", create_fixture(), "application/pdf")
    })
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["declared_form_code"] == "IMM5476"
    assert report["declared_form_code_verified"] is False
    assert report["template_source_verified"] is False
    assert report["bytes_persisted"] is False
    assert report["official_pdf_autofill_supported"] is False

    wrong = client.post(url, data={"form_code": "MALICIOUS"}, files={
        "file": ("form.pdf", create_fixture(), "application/pdf")
    })
    assert wrong.status_code == 422

    identity["sub"] = "not-a-member"
    unauthorized = client.post(url, data={"form_code": "IMM5476"}, files={
        "file": ("form.pdf", create_fixture(), "application/pdf")
    })
    assert unauthorized.status_code == 404
