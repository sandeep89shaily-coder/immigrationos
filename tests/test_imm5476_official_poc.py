"""Synthetic PDF regression tests for the authentic-form incremental-fill PoC.

The real government PDF is deliberately not checked into the repo; validation
against it is separately demonstrated using its fixed SHA-256 and CLI.
"""
from hashlib import sha256
from io import BytesIO
import xml.etree.ElementTree as ET

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, TextStringObject,
)
from reportlab.pdfgen.canvas import Canvas

from app import imm5476_official_poc as poc


def synthetic_blank():
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(620, 930))
    for i, binding in enumerate(poc._FIELDS.values()):
        canvas.acroForm.textfield(name=binding.acroform_name, x=25, y=40 + 45 * i,
                                   width=400, height=22, forceBorder=True)
    canvas.save()
    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(buffer.getvalue())))
    acro = writer._root_object["/AcroForm"].get_object()
    xfa_root = ET.Element("{http://www.xfa.org/schema/xfa-data/1.0/}datasets")
    data_node = ET.SubElement(xfa_root, "{http://www.xfa.org/schema/xfa-data/1.0/}data")
    for binding in poc._FIELDS.values():
        node = data_node
        for name, index in binding.xfa_path:
            matches = [e for e in node if e.tag == name]
            while len(matches) <= index:
                matches.append(ET.SubElement(node, name))
            node = matches[index]
    ds = DecodedStreamObject()
    ds.set_data(ET.tostring(xfa_root, encoding="utf-8", xml_declaration=True))
    template = DecodedStreamObject()
    template.set_data(b'<template xmlns="http://www.xfa.org/schema/xfa-template/3.6/"/>')
    acro[NameObject("/XFA")] = ArrayObject([
        TextStringObject("template"), writer._add_object(template),
        TextStringObject("datasets"), writer._add_object(ds),
    ])
    writer._root_object[NameObject("/Perms")] = DictionaryObject({
        NameObject("/UR3"): NameObject("/SyntheticTestOnly")})
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


def test_exact_version_and_safe_file_guards(tmp_path):
    blank = tmp_path / "wrong-template.pdf"
    blank.write_bytes(synthetic_blank())
    with pytest.raises(poc.IMM5476ExperimentBlocked, match="form|Form"):
        poc.generate_fictional_imm5476(blank, tmp_path / "out.pdf")
    assert not (tmp_path / "out.pdf").exists()


def test_incremental_pdf_preserves_original_and_both_form_layers(tmp_path, monkeypatch):
    raw = synthetic_blank()
    blank = tmp_path / "blank.pdf"
    blank.write_bytes(raw)
    monkeypatch.setattr(poc, "SOURCE_SHA256", sha256(raw).hexdigest())
    monkeypatch.setattr(poc, "PAGE_COUNT", 1)
    output = tmp_path / "fictional.pdf"
    report = poc.generate_fictional_imm5476(blank, output)
    assert report["fictional_fields_verified"] == len(poc._FIELDS)
    assert report["ready_for_submission"] is False
    assert report["adobe_reader_validation_verified"] is False
    assert output.read_bytes().startswith(raw)
    read = PdfReader(output)
    assert len(read.pages) == 1
    assert read.get_fields()[poc._FIELDS["applicant_given"].acroform_name]["/V"] == "Aarav"
    packet = poc._find_xfa_packet(read, "datasets").get_object().get_data()
    xml = poc._parse_xml(packet)
    assert poc._xfa_leaf(xml, poc._FIELDS["applicant_given"].xfa_path).text == "Aarav"
    assert poc._xfa_leaf(xml, poc._FIELDS["representative_family"].xfa_path).text == "Kapoor"
    with pytest.raises(poc.IMM5476ExperimentBlocked, match="overwrit"):
        poc.generate_fictional_imm5476(blank, output)


def test_missing_xfa_path_fails_before_output_is_written(tmp_path, monkeypatch):
    raw = synthetic_blank()
    blank = tmp_path / "blank.pdf"
    blank.write_bytes(raw)
    monkeypatch.setattr(poc, "SOURCE_SHA256", sha256(raw).hexdigest())
    monkeypatch.setattr(poc, "PAGE_COUNT", 1)
    wrong = dict(poc._FIELDS)
    wrong["applicant_given"] = poc.FieldBinding(
        wrong["applicant_given"].acroform_name,
        (("IMM_5476", 0), ("Page1", 0), ("DoesNotExist", 0)))
    monkeypatch.setattr(poc, "_FIELDS", wrong)
    with pytest.raises(poc.IMM5476ExperimentBlocked, match="mapping|binding|missing|changed"):
        poc.generate_fictional_imm5476(blank, tmp_path / "out.pdf")
    assert not (tmp_path / "out.pdf").exists()

def test_concatenated_xfa_document_has_one_xml_declaration(tmp_path, monkeypatch):
    """Adobe parses all XFA packet streams as one XDP document."""
    raw = synthetic_blank()
    blank = tmp_path / "blank.pdf"
    blank.write_bytes(raw)
    monkeypatch.setattr(poc, "SOURCE_SHA256", sha256(raw).hexdigest())
    monkeypatch.setattr(poc, "PAGE_COUNT", 1)
    result = tmp_path / "result.pdf"
    poc.generate_fictional_imm5476(blank, result)
    read = PdfReader(result)
    xfa = read.trailer["/Root"]["/AcroForm"].get_object()["/XFA"]
    joined = b"".join(xfa[i+1].get_object().get_data() for i in range(0, len(xfa), 2))
    parsed = poc._parse_xml(joined)
    assert parsed.tag.endswith("xdp") or parsed.tag.endswith("datasets")
    assert joined.count(b"<?xml") <= 1
