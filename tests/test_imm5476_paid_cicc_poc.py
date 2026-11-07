"""Synthetic-only tests for IMM5476 paid-CICC appointment XDP generation."""
import copy
import xml.etree.ElementTree as ET

import pytest

from app import imm5476_paid_cicc_poc as poc


def _blank_dataset():
    """Mimic observed XFA hierarchy, including repeated office and surnames."""
    root = ET.Element(f"{{{poc._XFA}}}datasets")
    ET.SubElement(root, f"{{{poc._XFA}}}data")

    def ensure(path):
        cur = root[0]
        for name, index in path:
            found = [ch for ch in cur if poc._local(ch.tag) == name]
            while len(found) <= index:
                ET.SubElement(cur, name)
                found = [ch for ch in cur if poc._local(ch.tag) == name]
            cur = found[index]
        return cur

    for path in list(poc.TEXT_PATHS.values()) + list(poc.RADIO_PATHS.values()) + [poc.UNPAID]:
        ensure(path)
    for key in ("applicant_family", "representative_family"):
        family = ensure(poc.TEXT_PATHS[key])
        body = ET.SubElement(family, "{http://www.w3.org/1999/xhtml}body")
        p = ET.SubElement(body, "{http://www.w3.org/1999/xhtml}p")
        ET.SubElement(p, "{http://www.w3.org/1999/xhtml}span").text = "\N{NO-BREAK SPACE}"
    for path in (
        poc.SECTION_B + (("question8", 0), ("signatrureApplicant", 0)),
        poc.SECTION_B + (("question8", 0), ("dateSigned", 0)),
        poc.BASE + (("sectionE", 0), ("signatrureApplicant", 0)),
        poc.BASE + (("sectionE", 0), ("dateApplicantSigned", 0)),
    ):
        ensure(path)
    return root


def test_fixed_map_reproduces_real_observed_pdf_names():
    assert len(poc.TEXT_PATHS) == 21
    assert set(poc.TEXT_PATHS) == set(poc.FICTIONAL_VALUES)
    assert poc.full_pdf_name(poc.TEXT_PATHS["applicant_email"]).endswith(
        "SectionA[0].office[0]")
    assert poc.full_pdf_name(poc.TEXT_PATHS["application_type"]).endswith(
        "SectionA[0].office[2]")
    assert poc.full_pdf_name(poc.TEXT_PATHS["cicc_membership"]).endswith(
        "questionII[0].ICCRCMember[0]")


def test_dataset_populates_21_fields_two_radios_and_no_signatures():
    root = _blank_dataset()
    poc.populate_fictional_dataset(root)
    for key, path in poc.TEXT_PATHS.items():
        assert poc.node(root, path).text == poc.FICTIONAL_VALUES[key]
    for path in poc.RADIO_PATHS.values():
        assert poc.node(root, path).text == "1"
    assert poc.node(root, poc.UNPAID).text is None
    for entry in root.iter():
        if poc._local(entry.tag) in poc.PROTECTED_FIELDS:
            assert not (entry.text or "").strip()


def test_exported_xdp_declares_namespace_on_datasets_packet():
    root = _blank_dataset()
    poc.populate_fictional_dataset(root)
    encoded = poc.serialize_vendor_safe_xdp(root)
    parsed = ET.fromstring(encoded)
    packet = next(iter(parsed))
    assert packet.tag == f"{{{poc._XFA}}}datasets"
    assert b'<xfa:datasets xmlns:xfa=' in encoded
    # Simulate a vendor exporting ONLY this packet, without the XDP wrapper.
    packet_only = ET.tostring(packet, encoding="utf-8")
    assert ET.fromstring(packet_only).tag == packet.tag
    assert not b'<!DOCTYPE' in encoded
    for key, path in poc.TEXT_PATHS.items():
        assert poc.node(packet, path).text == poc.FICTIONAL_VALUES[key]


def test_refuses_double_population_and_unexpected_richtext():
    root = _blank_dataset()
    poc.populate_fictional_dataset(root)
    with pytest.raises(ValueError, match="Source must be blank"):
        poc.populate_fictional_dataset(root)
    malformed = _blank_dataset()
    surname = poc.node(malformed, poc.TEXT_PATHS["applicant_family"])
    surname.clear()
    with pytest.raises(ValueError, match="rich-text surname"):
        poc.populate_fictional_dataset(malformed)


def test_rejects_preselected_unpaid_option_and_nonblank_signature():
    root = _blank_dataset()
    poc.node(root, poc.UNPAID).text = "1"
    with pytest.raises(ValueError, match="Unpaid choice"):
        poc.populate_fictional_dataset(root)
    other = _blank_dataset()
    signature = poc.node(other, poc.SECTION_B + (
        ("question8", 0), ("signatrureApplicant", 0)))
    signature.text = "Forged Example"
    with pytest.raises(ValueError, match="signature"):
        poc.populate_fictional_dataset(other)


def test_refuses_unapproved_pdf_bytes_without_writing(tmp_path):
    fake_pdf = b"%PDF-1.7\nSYNTHETIC-NOT-IRCC"
    with pytest.raises(ValueError, match="Unapproved"):
        poc.generate_fictional_paid_cicc_xdp(fake_pdf)
    assert not list(tmp_path.iterdir())


def test_acrobat_regression_rejects_escaped_xhtml_in_surname_dataset():
    from scripts.verify_imm5476_paid_cicc import is_plain_surname_node

    scalar = ET.Element("familyName")
    scalar.text = "Sharma"
    assert is_plain_surname_node(scalar, "Sharma")

    # This was the actual previous Qoppa output. The XHTML was well-formed,
    # but Adobe displayed the markup *literally* in both surname fields.
    escaped_markup = ET.Element("familyName")
    escaped_markup.text = (
        '<body xmlns="http://www.w3.org/1999/xhtml">'
        '<p><span>Sharma</span></p></body>')
    assert not is_plain_surname_node(escaped_markup, "Sharma")

    rich_node = ET.Element("familyName")
    ET.SubElement(rich_node, "{http://www.w3.org/1999/xhtml}body").text = "Sharma"
    assert not is_plain_surname_node(rich_node, "Sharma")
    assert not is_plain_surname_node(scalar, "Kapoor")
