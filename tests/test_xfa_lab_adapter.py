"""Proof of XFA data writing on a synthetic form; NEVER an official IRCC form."""
from hashlib import sha256
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.xfa_lab_adapter import (
    LabXfaApproval, XfaDatasetBlocked, fill_synthetic_xfa_dataset, _packet_stream, _locate,
)
from app.xfa_probe import _xml
from tests.test_xfa_probe import with_xfa

TEMPLATE = b'<template xmlns="http://www.xfa.org/schema/xfa-template/2.5/"><subform><field name="GivenName"/></subform></template>'
DATA = (b'<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">'
        b'<xfa:data><Applicant><GivenName>Old</GivenName>'
        b'<FamilyName>Placeholder</FamilyName></Applicant></xfa:data></xfa:datasets>')
PATHS = frozenset({("Applicant", "GivenName"), ("Applicant", "FamilyName")})


def test_xfa_dataset_roundtrip_does_not_remove_template_packet():
    raw = with_xfa([("template", TEMPLATE), ("datasets", DATA)])
    approval = LabXfaApproval(sha256(raw).hexdigest(), PATHS, synthetic_only=True)
    result = fill_synthetic_xfa_dataset(raw, {
        ("Applicant", "GivenName"): "Fictional",
        ("Applicant", "FamilyName"): "Sample",
    }, approval)
    assert result.startswith(b"%PDF-")
    original_reader = PdfReader(BytesIO(raw))
    resulting_reader = PdfReader(BytesIO(result))
    original_xfa = original_reader.trailer["/Root"]["/AcroForm"].get_object()["/XFA"]
    resulting_xfa = resulting_reader.trailer["/Root"]["/AcroForm"].get_object()["/XFA"]
    assert len(original_xfa) == len(resulting_xfa) == 4
    assert original_xfa[1].get_object().get_data() == resulting_xfa[1].get_object().get_data()
    _, _, updated = _packet_stream(resulting_reader.trailer["/Root"]["/AcroForm"].get_object())
    root = _xml(updated.get_data())
    assert _locate(root, ("Applicant", "GivenName")).text == "Fictional"
    assert _locate(root, ("Applicant", "FamilyName")).text == "Sample"


def test_rejects_unapproved_and_wrong_template():
    raw = with_xfa([("template", TEMPLATE), ("datasets", DATA)])
    values = {("Applicant", "GivenName"): "Fictional", ("Applicant", "FamilyName"): "Sample"}
    with pytest.raises(XfaDatasetBlocked):
        fill_synthetic_xfa_dataset(raw, values, LabXfaApproval(sha256(raw).hexdigest(), PATHS))
    with pytest.raises(XfaDatasetBlocked):
        fill_synthetic_xfa_dataset(raw, values, LabXfaApproval("0" * 64, PATHS, synthetic_only=True))
    with pytest.raises(XfaDatasetBlocked):
        fill_synthetic_xfa_dataset(raw, {("Applicant", "GivenName"): "Fictional"},
                                   LabXfaApproval(sha256(raw).hexdigest(), PATHS, synthetic_only=True))
    with pytest.raises(XfaDatasetBlocked):
        fill_synthetic_xfa_dataset(raw, {**values, ("Applicant", "DOB"): "Other"},
                                   LabXfaApproval(sha256(raw).hexdigest(), PATHS, synthetic_only=True))


def test_missing_and_ambiguous_xml_binding_fail_closed():
    missing = with_xfa([("template", TEMPLATE), ("datasets", DATA)])
    with pytest.raises(XfaDatasetBlocked):
        fill_synthetic_xfa_dataset(missing, {("Applicant", "DOB"): "2001-01-01"},
                                   LabXfaApproval(sha256(missing).hexdigest(),
                                                  frozenset({("Applicant", "DOB")}), synthetic_only=True))
    duplicated = DATA.replace(b'</Applicant>', b'<GivenName>Duplicate</GivenName></Applicant>')
    pdf = with_xfa([("template", TEMPLATE), ("datasets", duplicated)])
    with pytest.raises(XfaDatasetBlocked):
        fill_synthetic_xfa_dataset(pdf, {("Applicant", "GivenName"): "Fictional"},
                                   LabXfaApproval(sha256(pdf).hexdigest(),
                                                  frozenset({("Applicant", "GivenName")}), synthetic_only=True))
