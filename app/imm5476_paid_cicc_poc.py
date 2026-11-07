"""IMM5476 11-2025: fixed-fictional paid CICC appointment XDP proof of concept.

No applicant data, signing, production autofill or submission. The only
accepted source is the original, SHA-256 pinned four-page IRCC form.
The output is XDP data for import by an independently tested XFA engine.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from pypdf import PdfReader

from app.imm5476_official_poc import SOURCE_SHA256, _find_xfa_packet, _parse_xml

_XDP = "http://ns.adobe.com/xdp/"
_XFA = "http://www.xfa.org/schema/xfa-data/1.0/"
ET.register_namespace("xdp", _XDP)
ET.register_namespace("xfa", _XFA)

BASE = (("IMM_5476", 0), ("Page1", 0))
SECTION_A = BASE + (("SectionA", 0),)
SECTION_B = BASE + (("SectionB", 0),)
PAID = SECTION_B + (("question6", 0), ("questionII", 0))
CONTACT = SECTION_B + (("question7", 0),)

# Each path was inspected on the authentic uploaded IMM5476, not inferred
# from the label or the XFA template's possible future versions.
TEXT_PATHS = {
    "applicant_family": SECTION_A + (("familyName", 0),),
    "applicant_given": SECTION_A + (("givenName", 0),),
    "applicant_dob": SECTION_A + (("DOB", 0),),
    "applicant_email": SECTION_A + (("office", 0),),
    "application_type": SECTION_A + (("office", 2),),
    "application_number": SECTION_A + (("application", 0),),
    "uci": SECTION_A + (("UCI", 0),),
    "representative_family": SECTION_B + (("familyName", 0),),
    "representative_given": SECTION_B + (("givenName", 0),),
    "cicc_membership": PAID + (("ICCRCMember", 0),),
    "organization": CONTACT + (("organization", 0),),
    "unit": CONTACT + (("unit", 0),),
    "street_no": CONTACT + (("streetNo", 0),),
    "street_name": CONTACT + (("streetName", 0),),
    "city": CONTACT + (("city", 0),),
    "province": CONTACT + (("province", 0),),
    "country": CONTACT + (("country", 0),),
    "postal_code": CONTACT + (("postalcode", 0),),
    "phone_country_code": CONTACT + (("phoneCountryCode", 0),),
    "phone_number": CONTACT + (("phoneNumber", 0),),
    "representative_email": CONTACT + (("email", 0),),
}
FICTIONAL_VALUES = {
    "applicant_family": "Sharma",
    "applicant_given": "Aarav",
    "applicant_dob": "2001-06-09",
    "applicant_email": "aarav@example.test",
    "application_type": "Study permit",
    "application_number": "S000000000",
    "uci": "0000-0000",
    "representative_family": "Kapoor",
    "representative_given": "Anita",
    "cicc_membership": "R000000",
    "organization": "Fictional Maple Immigration",
    "unit": "100",
    "street_no": "123",
    "street_name": "Example Street",
    "city": "Toronto",
    "province": "Ontario",
    "country": "Canada",
    "postal_code": "M5V 0A0",
    "phone_country_code": "1",
    "phone_number": "4165550100",
    "representative_email": "anita@example.test",
}
assert len(TEXT_PATHS) == 21 and set(TEXT_PATHS) == set(FICTIONAL_VALUES)

RADIO_PATHS = {
    "appoint": BASE + (("RadioButtonList", 0),),
    "paid_cicc": PAID + (("compensated", 0),),
}
UNPAID = SECTION_B + (("question6", 0), ("questionI", 0), ("uncompensated", 0))
PROTECTED_FIELDS = frozenset({
    "signatrureApplicant", "dateSigned", "dateApplicantSigned", "dateSpouseSigned",
})
_XDP_HEADER = (b'<xdp:xdp xmlns:html="http://www.w3.org/1999/xhtml" '
               b'xmlns:xdp="http://ns.adobe.com/xdp/" '
               b'xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">'
               b'<xfa:datasets>')
_XDP_DATASET_LOCAL_NS = (
    b'<xdp:xdp xmlns:xdp="http://ns.adobe.com/xdp/">'
    b'<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" '
    b'xmlns:html="http://www.w3.org/1999/xhtml">'
)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def node(root: ET.Element, path: tuple[tuple[str, int], ...]) -> ET.Element:
    data = [e for e in root if _local(e.tag) == "data"]
    if len(data) != 1:
        raise ValueError("Expected one XFA data node")
    cur = data[0]
    for name, index in path:
        matches = [e for e in cur if _local(e.tag) == name]
        if index < 0 or index >= len(matches):
            raise ValueError("Official XFA binding missing: " + name)
        cur = matches[index]
    return cur


def full_pdf_name(path: tuple[tuple[str, int], ...]) -> str:
    return ".".join(f"{name}[{index}]" for name, index in path)


def populate_fictional_dataset(root: ET.Element) -> None:
    """Set only observed text and two appointment controls; do not touch declarations."""
    for key, path in TEXT_PATHS.items():
        target = node(root, path)
        if key.endswith("_family"):
            if len(target) != 1 or _local(target[0].tag) != "body":
                raise ValueError("Unexpected rich-text surname source")
            for child in list(target):
                target.remove(child)
        elif len(target):
            raise ValueError("Unexpected nested text field structure")
        if (target.text or "").strip():
            raise ValueError("Source must be blank: " + key)
        target.text = FICTIONAL_VALUES[key]
    for path in RADIO_PATHS.values():
        target = node(root, path)
        if len(target) or (target.text or "").strip():
            raise ValueError("Source radio not blank")
        # The observed first export item is "1"; Qoppa's AcroForm on-state
        # "0" is set using its native radio API separately, not PDF patching.
        target.text = "1"
    if (node(root, UNPAID).text or "").strip():
        raise ValueError("Unpaid choice should be unselected")
    for item in root.iter():
        if _local(item.tag) in PROTECTED_FIELDS and (item.text or "").strip():
            raise ValueError("Unexpected signature or declaration date content")


def serialize_vendor_safe_xdp(dataset: ET.Element) -> bytes:
    xdp = ET.Element(f"{{{_XDP}}}xdp")
    xdp.append(dataset)
    xml = ET.tostring(xdp, encoding="utf-8", xml_declaration=True)
    # The XFA SDK exports the datasets packet without its enclosing XDP.
    # Namespace declarations MUST be on the dataset packet itself; otherwise
    # the generated PDF has an unbound xfa: prefix and Acrobat may reject it.
    if xml.count(_XDP_HEADER) != 1:
        raise ValueError("XDP namespace layout changed")
    xml = xml.replace(_XDP_HEADER, _XDP_DATASET_LOCAL_NS)
    parsed = _parse_xml(xml)
    if parsed.tag != f"{{{_XDP}}}xdp":
        raise ValueError("Expected xdp document root")
    child = next(iter(parsed))
    if child.tag != f"{{{_XFA}}}datasets":
        raise ValueError("Expected XFA datasets packet")
    for key, path in TEXT_PATHS.items():
        if node(child, path).text != FICTIONAL_VALUES[key]:
            raise ValueError("XFA roundtrip mismatch: " + key)
    for path in RADIO_PATHS.values():
        if node(child, path).text != "1":
            raise ValueError("XFA radio roundtrip mismatch")
    return xml


def generate_fictional_paid_cicc_xdp(raw_original: bytes) -> bytes:
    """Generate data-only XDP from exact official PDF. Never mutates the PDF."""
    if len(raw_original) > 12 * 1024 * 1024 or sha256(raw_original).hexdigest() != SOURCE_SHA256:
        raise ValueError("Unapproved government form revision")
    reader = PdfReader(BytesIO(raw_original), strict=True)
    if len(reader.pages) != 4 or "/UR3" not in reader.trailer["/Root"]["/Perms"].get_object():
        raise ValueError("Official page count or usage-rights baseline changed")
    fields = reader.get_fields() or {}
    for path in TEXT_PATHS.values():
        field = fields.get(full_pdf_name(path))
        if field is None or str(field.get("/FT")) != "/Tx" or field.get("/V") not in (None, ""):
            raise ValueError("Observed PDF text field changed or is nonblank")
    for path in RADIO_PATHS.values():
        field = fields.get(full_pdf_name(path))
        if field is None or str(field.get("/FT")) != "/Btn":
            raise ValueError("Observed radio control changed")
    original = _find_xfa_packet(reader, "datasets").get_object().get_data()
    parsed = _parse_xml(original)
    populate_fictional_dataset(parsed)
    return serialize_vendor_safe_xdp(parsed)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Fictional IMM5476 paid-CICC XDP experiment only")
    parser.add_argument("official_blank_pdf", type=Path)
    parser.add_argument("new_xdp_output", type=Path)
    args = parser.parse_args()
    if args.new_xdp_output.exists() or args.official_blank_pdf.resolve() == args.new_xdp_output.resolve():
        raise SystemExit("Refusing to overwrite existing output or the original PDF")
    xml = generate_fictional_paid_cicc_xdp(args.official_blank_pdf.read_bytes())
    args.new_xdp_output.write_bytes(xml)
    print("Generated 21 fictional text fields + 2 radio selections as XDP only. "
          "No signatures, client data, PDF modifications or submission support.")


if __name__ == "__main__":
    main()
