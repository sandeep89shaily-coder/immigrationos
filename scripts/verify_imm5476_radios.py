"""Independent 12-text + 2-radio XFA/AcroForm experiment verification.

The source IRCC PDF must match the pinned official SHA-256. This test
recognizes both visible button ON states and XFA data item values.
It does NOT certify Adobe Reader, signatures or IRCC submit-ability.
"""
from argparse import ArgumentParser
import json
from pathlib import Path

import fitz
from pypdf import PdfReader

from app.imm5476_official_poc import _find_xfa_packet, _parse_xml
from scripts.imm5476_xdp_vendor_trial import verify as verify_text


_RADIO_GROUPS = {
    "appointment": (
        "IMM_5476[0].Page1[0].RadioButtonList[0]",
        ["0", "Off", "Off", "Off", "Off"]),
    "unpaid": (
        "IMM_5476[0].Page1[0].SectionB[0].question6[0].questionI[0].uncompensated[0]",
        ["Off", "Off", "Off", "Off", "Off"]),
    "paid_cicc": (
        "IMM_5476[0].Page1[0].SectionB[0].question6[0].questionII[0].compensated[0]",
        ["0", "Off", "Off"]),
}
_XFA_DATA = {"RadioButtonList": "1", "uncompensated": None, "compensated": "1"}


def verify_radios(blank: Path, generated: Path, report_path: Path) -> bool:
    text_ok = verify_text(blank, generated, report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report.update({
        "two_radio_choices_tested": True,
        "adobe_reader_tested": False,
        "official_validated": False,
        "submission_ready": False,
    })
    try:
        with fitz.open(generated) as doc:
            groups = {}
            for page in doc:
                for widget in page.widgets() or []:
                    if widget.field_type_string == "RadioButton":
                        groups.setdefault(widget.field_name, []).append(
                            str(widget.field_value))
        group_matches = {
            name: groups.get(full_path) == expected
            for name, (full_path, expected) in _RADIO_GROUPS.items()
        }
        reader = PdfReader(generated, strict=False)
        root = _parse_xml(
            _find_xfa_packet(reader, "datasets").get_object().get_data())
        xfa_matches = {}
        for field_name, expected in _XFA_DATA.items():
            nodes = [node for node in root.iter()
                     if node.tag.rsplit("}", 1)[-1] == field_name]
            xfa_matches[field_name] = (
                len(nodes) == 1 and len(nodes[0]) == 0
                and nodes[0].text == expected)
        radio_ok = all(group_matches.values()) and all(xfa_matches.values())
        report["radio_acroform_matches"] = group_matches
        report["radio_xfa_matches"] = xfa_matches
        report["radio_layers_consistent"] = radio_ok
        report["status"] = (
            "twelve_text_two_radio_layers_pass_pre_adobe"
            if text_ok and radio_ok else "radio_or_text_layer_failure")
    except Exception as exc:
        report["radio_layers_consistent"] = False
        report["status"] = "radio_readback_error"
        report["radio_error_type"] = type(exc).__name__
        report["radio_error"] = str(exc)[:240]
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return report["status"] == "twelve_text_two_radio_layers_pass_pre_adobe"


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("blank", type=Path)
    parser.add_argument("filled", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    if not verify_radios(args.blank, args.filled, args.report):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
