"""Read-only verification of a fictional Qoppa IMM5476 paid-CICC XFA output.

Requires the original hash-pinned IRCC PDF, a generated PDF, and a report path.
No PDF modification, Adobe approval, signature validation or official support.
"""
from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from pypdf.generic import NullObject
import argparse

import fitz
from pypdf import PdfReader

from app.imm5476_paid_cicc_poc import (
    SOURCE_SHA256, TEXT_PATHS, FICTIONAL_VALUES, RADIO_PATHS,
    node, full_pdf_name, _local,
)
from app.imm5476_official_poc import _find_xfa_packet, _parse_xml


RADIO_EXPECTATIONS = {
    "appoint": ("IMM_5476[0].Page1[0].RadioButtonList[0]",
                ["0", "Off", "Off", "Off", "Off"]),
    "paid_cicc": (
        "IMM_5476[0].Page1[0].SectionB[0].question6[0].questionII[0].compensated[0]",
        ["0", "Off", "Off"]),
    "unpaid_off": (
        "IMM_5476[0].Page1[0].SectionB[0].question6[0].questionI[0].uncompensated[0]",
        ["Off"] * 5),
}


def is_plain_surname_node(element: ET.Element, expected: str) -> bool:
    """Raw XHTML-as-text is NOT valid, even when that XHTML parses as XML.

    The previous Qoppa output stored '<body>...</body>' in element.text;
    actual Acrobat displayed that markup literally. Require true scalar XFA
    content for the *explicitly plain-mode* vendor experiment.
    """
    return len(element) == 0 and element.text == expected


def verify(original_pdf: Path, generated_pdf: Path) -> dict:
    original_bytes = original_pdf.read_bytes()
    filled_bytes = generated_pdf.read_bytes()
    if sha256(original_bytes).hexdigest() != SOURCE_SHA256:
        raise ValueError("Official IMM5476 SHA-256 mismatch")
    if len(filled_bytes) > 20 * 1024 * 1024 or not filled_bytes.startswith(b"%PDF-"):
        raise ValueError("Output is not a reasonable generated PDF")
    original = PdfReader(original_pdf, strict=True)
    filled = PdfReader(generated_pdf, strict=False)
    packets = filled.trailer["/Root"]["/AcroForm"].get_object()["/XFA"].get_object()
    if len(packets) % 2 or len(packets) != 20:
        raise ValueError("Unexpected XFA packet count")
    whole = b"".join(packets[i + 1].get_object().get_data()
                     for i in range(0, len(packets), 2))
    parsed_whole = _parse_xml(whole)
    dataset = _parse_xml(_find_xfa_packet(filled, "datasets").get_object().get_data())
    widgets = {}
    with fitz.open(generated_pdf) as document:
        for page in document:
            for field in page.widgets() or []:
                widgets.setdefault(field.field_name, []).append(
                    (field.field_type_string, str(field.field_value)))
    text_status = {}
    surname_data_plain = {}
    for key, path in TEXT_PATHS.items():
        field_node = node(dataset, path)
        value = FICTIONAL_VALUES[key]
        if key.endswith("_family"):
            matches = is_plain_surname_node(field_node, value)
            surname_data_plain[key] = matches
        else:
            matches = len(field_node) == 0 and field_node.text == value
        visual_data = widgets.get(full_pdf_name(path)) == [("Text", value)]
        text_status[key] = matches and visual_data
    surname_widgets = {}
    for page in filled.pages:
        for ref in page.get("/Annots", []):
            annot = ref.get_object()
            for key in ("applicant_family", "representative_family"):
                if (str(annot.get("/T", "")) == "familyName[0]" and
                        str(annot.get("/V", "")) == FICTIONAL_VALUES[key]):
                    matches_plain = (
                        not int(annot.get("/Ff", 0)) & (1 << 25)
                        and (annot.get("/RV") is None or
                             isinstance(annot.get("/RV"), NullObject))
                    )
                    surname_widgets.setdefault(key, []).append(matches_plain)
    surname_structure_ok = (
        len(surname_widgets) == 2
        and all(value == [True] for value in surname_widgets.values())
        and len(surname_data_plain) == 2
        and all(surname_data_plain.values())
    )
    xfa_radio = {}
    for name, path in RADIO_PATHS.items():
        xfa_radio[name] = node(dataset, path).text == "1"
    unpaid = [e for e in dataset.iter() if _local(e.tag) == "uncompensated"]
    xfa_radio["unpaid_off"] = len(unpaid) == 1 and not (unpaid[0].text or "").strip()
    radio_status = {}
    for key, (field_name, expected) in RADIO_EXPECTATIONS.items():
        radio_status[key] = (
            [state for kind, state in widgets.get(field_name, [])
             if kind == "RadioButton"] == expected
            and xfa_radio[key])
    signature_status = {}
    for name in original.get_fields() or {}:
        if any(part in name for part in ("signatrureApplicant", "dateSigned",
                                         "dateApplicantSigned", "dateSpouseSigned")):
            signature_status[name] = all(val in ("", "None")
                                         for _, val in widgets.get(name, []))
    byte_range = [
        int(x) for x in
        original.trailer["/Root"]["/Perms"]["/UR3"].get_object()["/ByteRange"]]
    if len(byte_range) != 4 or any(x < 0 for x in byte_range) or (
            byte_range[0] + byte_range[1] > len(original_bytes) or
            byte_range[2] + byte_range[3] > len(original_bytes)):
        raise ValueError("Unsafe original usage-rights byte range")
    def signed(data):
        return (data[byte_range[0]:byte_range[0] + byte_range[1]] +
                data[byte_range[2]:byte_range[2] + byte_range[3]])
    warnings = []
    if not surname_structure_ok:
        warnings.append("Surname XFA data or PDF flags still contain rich-text XML")
    try:
        filled.get_fields()
    except Exception as exc:
        warnings.append("PDF field parser raised " + type(exc).__name__)
    report = {
        "form_code": "IMM5476",
        "template_revision": "11-2025",
        "fictional_data_only": True,
        "source_sha256": SOURCE_SHA256,
        "output_sha256": sha256(filled_bytes).hexdigest(),
        "pages": len(filled.pages),
        "entire_xdp_parses": _local(parsed_whole.tag) == "xdp",
        "text_fields_match_both_layers": sum(text_status.values()),
        "expected_text_fields": len(TEXT_PATHS),
        "radio_groups_match_both_layers": radio_status,
        "signatures_and_signature_dates_unpopulated": (
            bool(signature_status) and all(signature_status.values())),
        "original_bytes_untouched_prefix": filled_bytes.startswith(original_bytes),
        "original_ur3_signed_bytes_unchanged": signed(filled_bytes) == signed(original_bytes),
        "warnings": warnings,
        "plain_surname_data_valid": surname_structure_ok,
        "plain_surname_field_details": {
            key: {"xfa_scalar": surname_data_plain[key],
                  "no_richtext_pdf_flag_or_rv": surname_widgets.get(key) == [True]}
            for key in ("applicant_family", "representative_family")
        },
        "adobe_acrobat_tested": False,
        "commercial_license_verified": False,
        "submission_ready": False,
        "official_ircc_validated": False,
    }
    report["pre_adobe_structural_trial_pass"] = (
        report["pages"] == 4 and report["entire_xdp_parses"] and
        report["text_fields_match_both_layers"] == len(TEXT_PATHS) and
        all(radio_status.values()) and
        report["signatures_and_signature_dates_unpopulated"] and
        report["plain_surname_data_valid"] and
        report["original_ur3_signed_bytes_unchanged"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("official_blank", type=Path)
    parser.add_argument("vendor_output", type=Path)
    parser.add_argument("report_path", type=Path)
    args = parser.parse_args()
    result = verify(args.official_blank, args.vendor_output)
    if args.report_path.exists():
        raise SystemExit("Report output already exists")
    args.report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["pre_adobe_structural_trial_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
