"""Synthetic AcroForm tests only: no official IRCC PDF is certified here."""
from dataclasses import replace
from hashlib import sha256
from io import BytesIO

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app.pdf_form_adapter import PDFAdapterBlocked, StaticAcroFormApproval, fill_static_acroform


def synthetic_form():
    destination = BytesIO()
    c = canvas.Canvas(destination, pagesize=(450, 400))
    c.drawString(40, 360, "Synthetic immigration test fixture — NOT AN IRCC FORM")
    c.acroForm.textfield(name="given_name", x=40, y=300, width=220, height=22,
                         borderWidth=1, forceBorder=True)
    c.acroForm.textfield(name="family_name", x=40, y=250, width=220, height=22,
                         borderWidth=1, forceBorder=True)
    c.save()
    return destination.getvalue()


def approved(pdf):
    return StaticAcroFormApproval(
        form_code="SYNTHETIC",
        official_revision="test-only-1",
        template_sha256=sha256(pdf).hexdigest(),
        approved_fields=frozenset({"given_name", "family_name"}),
        approved_for_static_fill=True,
        requires_barcode_validation=False,
        approval_record="test-only fixture: synthetic content, no official form",
    )


def test_static_fixture_fills_exact_approved_fields_and_roundtrips():
    pdf = synthetic_form()
    values = {"given_name": "Sample", "family_name": "Applicant"}
    filled = fill_static_acroform(pdf, values, approved(pdf))
    result = PdfReader(BytesIO(filled))
    assert result.get_fields()["given_name"].get("/V") == "Sample"
    assert result.get_fields()["family_name"].get("/V") == "Applicant"


def test_no_default_approval_and_barcode_forms_are_denied():
    pdf = synthetic_form()
    a = approved(pdf)
    values = {"given_name": "A", "family_name": "B"}
    with pytest.raises(PDFAdapterBlocked, match="approved static"):
        fill_static_acroform(pdf, values, replace(a, approved_for_static_fill=False))
    with pytest.raises(PDFAdapterBlocked, match="approved static"):
        fill_static_acroform(pdf, values, replace(a, requires_barcode_validation=True))


def test_tampered_template_and_unmapped_fields_denied():
    pdf = synthetic_form()
    a = approved(pdf)
    values = {"given_name": "A", "family_name": "B"}
    with pytest.raises(PDFAdapterBlocked, match="checksum"):
        fill_static_acroform(pdf + b"x", values, a)
    with pytest.raises(PDFAdapterBlocked, match="mapping"):
        fill_static_acroform(pdf, {"given_name": "A"}, a)
    with pytest.raises(PDFAdapterBlocked, match="mapping"):
        fill_static_acroform(pdf, {**values, "extra": "C"}, a)
    bad = replace(a, approved_fields=frozenset({"given_name", "unknown"}))
    with pytest.raises(PDFAdapterBlocked, match="names changed"):
        fill_static_acroform(pdf, {"given_name": "A", "unknown": "C"}, bad)


def test_non_pdf_and_empty_input_denied():
    pdf = synthetic_form()
    with pytest.raises(PDFAdapterBlocked):
        fill_static_acroform(b"NOT PDF", {"given_name": "A", "family_name": "B"}, approved(pdf))
    with pytest.raises(PDFAdapterBlocked):
        fill_static_acroform(pdf, {"given_name": "A", "family_name": "X" * 1001}, approved(pdf))


def test_no_field_without_review_evidence():
    with pytest.raises(PDFAdapterBlocked):
        StaticAcroFormApproval("SYNTHETIC", "", "0" * 64, frozenset({"name"}))
