"""Read-only verification of a fictional Qoppa IMM5476 paid-CICC XFA output.

Requires the original hash-pinned IRCC PDF, a generated PDF, and a report path.
No PDF modification, Adobe approval, signature validation or official support.
"""
from hashlib import sha256
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
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
    malformed_surname_xml = []
    for key, path in TEXT_PATHS.items():
        stored = node(dataset, path).text or ""
        value = FICTIONAL_VALUES[key]
        if key.endswith("_family"):
            matches = bool(re.search(r">" + re.escape(value) + r"</span>", stored))
            try:
                ET.fromstring(stored)
            except ET.ParseError:
                malformed_surname_xml.append(key)
        else:
            matches = stored == value
        visual_data = widgets.get(full_pdf_name(path)) == [("Text", value)]
        text_status[key] = matches and visual_data
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
    if malformed_surname_xml:
        warnings.append("Vendor-generated surname XHTML is not well-formed")
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
