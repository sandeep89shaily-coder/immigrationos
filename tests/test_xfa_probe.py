"""Safe structural XFA packet probing using synthetic PDFs only."""
from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, NameObject, TextStringObject

from app.form_template_inspector import inspect_pdf_template
from app.xfa_probe import XfaProbeError, probe_xfa
from tests.test_form_template_inspector import create_fixture


TEMPLATE = b'<template xmlns="http://www.xfa.org/schema/xfa-template/2.5/"><subform layout="flowed"><occur min="1" max="-1"/></subform></template>'
DATASETS = b'<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/"><xfa:data><Synthetic/></xfa:data></xfa:datasets>'


def stream(blob):
    obj = DecodedStreamObject()
    obj.set_data(blob)
    return obj


def with_xfa(packets):
    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(create_fixture())))
    acro = writer._root_object["/AcroForm"].get_object()
    parts = ArrayObject()
    for name, payload in packets:
        parts.extend([TextStringObject(name), writer._add_object(stream(payload))])
    acro[NameObject("/XFA")] = parts
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_named_xfa_packet_inventory_is_structural_and_never_approves_filling():
    raw = with_xfa([("template", TEMPLATE), ("datasets", DATASETS)])
    result = inspect_pdf_template(raw)
    assert result["classification"] == "xfa_or_hybrid_requires_adobe_workflow"
    xfa = result["xfa_structure"]
    assert xfa["packet_names"] == ["template", "datasets"]
    assert xfa["template_packet_present"] is True
    assert xfa["datasets_packet_present"] is True
    assert "flowed_subform" in xfa["dynamic_indicators"]
    assert xfa["xfa_fill_supported"] is False
    assert result["official_pdf_autofill_supported"] is False


def test_single_xfa_stream_is_supported_for_structural_inventory():
    xdp = b'<xdp:xdp xmlns:xdp="http://ns.adobe.com/xdp/"><template/><datasets/></xdp:xdp>'
    parsed = probe_xfa(stream(xdp))
    assert parsed["xfa_container"] == "single_stream"
    assert parsed["packet_names"] == ["complete_xdp"]
    assert parsed["datasets_packet_present"] is True


@pytest.mark.parametrize("bad", [
    b'<!DOCTYPE x [<!ENTITY leak SYSTEM "file:///etc/passwd">]><x/>',
    b'<!ENTITY leak SYSTEM "https://example.test/x"><x/>',
    b'<template>',
    b'<x>' + b'a' * (3 * 1024 * 1024 + 1) + b'</x>',
])
def test_xml_entities_malformed_and_oversize_are_rejected(bad):
    with pytest.raises(XfaProbeError):
        probe_xfa(stream(bad))


def test_malformed_xfa_packet_is_marked_uninspectable_without_approval():
    raw = with_xfa([("template", b'<broken>')])
    result = inspect_pdf_template(raw)
    assert "xfa_structure_uninspectable" in result["indicators"]
    assert result["xfa_structure"] is None
    assert result["candidate_for_static_adapter"] is False


def test_duplicate_packets_rejected():
    with pytest.raises(XfaProbeError):
        probe_xfa(ArrayObject([TextStringObject("template"), stream(TEMPLATE),
                               TextStringObject("template"), stream(TEMPLATE)]))


def test_dynamic_render_indicator():
    cfg = b'<config><present><pdf><dynamicRender>required</dynamicRender></pdf></present></config>'
    r = probe_xfa(ArrayObject([TextStringObject("config"), stream(cfg)]))
    assert "dynamic_render_required" in r["dynamic_indicators"]
    assert r["xfa_layout_assessment"] == "dynamic_indicators_detected"
