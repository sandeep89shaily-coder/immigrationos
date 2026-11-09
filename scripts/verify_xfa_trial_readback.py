"""Independent, fail-closed readback of a fictional XFA PDF trial.

Not an IRCC or Adobe acceptance certificate. This validates only one fixed
subset of four IMM5476 synthetic fields, preserving the supplied original
byte prefix and independently reading XFA datasets and AcroForm values.
"""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from pypdf import PdfReader

IMM5476_SHA256 = "aca5c476b93d1c496b1afbc2cfe843499e852e31dcf0c192153bd01f8d6c56c4"
MAX_PDF_BYTES = 13 * 1024 * 1024
# These values are deliberately fictional, fixed, and never sourced from cases.
EXPECTED = {
    "IMM_5476[0].Page1[0].SectionA[0].familyName[0]": "Sharma",
    "IMM_5476[0].Page1[0].SectionA[0].givenName[0]": "Aarav",
    "IMM_5476[0].Page1[0].SectionB[0].familyName[0]": "Kapoor",
    "IMM_5476[0].Page1[0].SectionB[0].givenName[0]": "Anita",
}
_INDEX = re.compile(r"\[\d+\]$")


def _local(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _dataset_packets(reader):
    acro_ref = reader.trailer["/Root"].get("/AcroForm")
    if acro_ref is None:
        raise ValueError("missing_acroform")
    xfa = acro_ref.get_object().get("/XFA")
    if xfa is None:
        raise ValueError("missing_xfa")
    node = xfa.get_object()
    packets = []
    if isinstance(node, list):
        if len(node) % 2:
            raise ValueError("odd_length_xfa_array")
        for i in range(0, len(node), 2):
            if str(node[i]).lower() == "datasets":
                packets.append(node[i + 1].get_object().get_data())
    else:
        raw = node.get_data()
        packets = [raw]
    if len(packets) != 1:
        raise ValueError("missing_or_ambiguous_xfa_datasets_packet")
    if len(packets[0]) > MAX_PDF_BYTES:
        raise ValueError("oversized_xfa_packet")
    try:
        root = ET.fromstring(packets[0])
    except ET.ParseError as exc:
        raise ValueError("invalid_xfa_xml") from exc
    if _local(root.tag) != "datasets":
        roots = [e for e in root.iter() if _local(e.tag) == "datasets"]
        if len(roots) != 1:
            raise ValueError("missing_or_ambiguous_datasets_root")
        root = roots[0]
    return root


def _dataset_values(root):
    """Match the full schema path, not only ambiguous familyName/givenName."""
    paths = {}
    def visit(element, parts):
        current = (*parts, _local(element.tag))
        if len(element) == 0:
            text = (element.text or "").strip()
            paths.setdefault(tuple(current), []).append(text)
        else:
            for child in element:
                visit(child, current)
    visit(root, ())
    checked = {}
    for full_name, expected in EXPECTED.items():
        wanted = tuple(_INDEX.sub("", x) for x in full_name.split("."))
        matches = [v for parts, values in paths.items()
                   if len(parts) >= len(wanted) and parts[-len(wanted):] == wanted
                   for v in values]
        checked[full_name] = len(matches) == 1 and matches[0] == expected
    return checked


def verify(original: bytes, output: bytes, *, expected_input_hash: str,
           official: bool = False) -> dict:
    result = {
        "schema_version": "xfa-independent-readback-v1",
        "status": "blocked",
        "official_source_sha256_verified": False,
        "technical_subset_readback_verified": False,
        "adobe_reader_tested": False,
        "ircc_form_validated": False,
        "government_submission_supported": False,
        "fictional_test_values_only": True,
    }
    try:
        if (len(expected_input_hash) != 64 or
                not re.fullmatch(r"[0-9a-f]{64}", expected_input_hash)):
            raise ValueError("invalid_expected_input_hash")
        if (not original.startswith(b"%PDF-") or
                not output.startswith(b"%PDF-") or
                max(len(original), len(output)) > MAX_PDF_BYTES):
            raise ValueError("invalid_or_oversized_pdf")
        input_hash = sha256(original).hexdigest()
        result["original_sha256"] = input_hash
        result["output_sha256"] = sha256(output).hexdigest()
        if input_hash != expected_input_hash:
            raise ValueError("original_checksum_mismatch")
        if official and input_hash != IMM5476_SHA256:
            raise ValueError("not_sha_pinned_official_imm5476")
        result["official_source_sha256_verified"] = official
        if len(output) <= len(original) or not output.startswith(original):
            raise ValueError("signed_original_prefix_not_preserved")
        result["original_prefix_preserved"] = True
        original_reader = PdfReader(BytesIO(original), strict=True)
        reader = PdfReader(BytesIO(output), strict=True)
        if original_reader.is_encrypted or reader.is_encrypted:
            raise ValueError("encrypted_pdf")
        if len(original_reader.pages) != len(reader.pages):
            raise ValueError("page_count_changed")
        if official and len(reader.pages) != 4:
            raise ValueError("unexpected_official_page_count")
        result["page_count"] = len(reader.pages)
        acro = reader.get_fields() or {}
        acro_matches = {
            key: str(acro.get(key, {}).get("/V", "")) == value
            for key, value in EXPECTED.items()
        }
        result["acroform_readback"] = {
            "expected": len(EXPECTED), "matched": sum(acro_matches.values())}
        xfa_matches = _dataset_values(_dataset_packets(reader))
        result["xfa_datasets_readback"] = {
            "expected": len(EXPECTED), "matched": sum(xfa_matches.values())}
        if not all(acro_matches.values()):
            raise ValueError("acroform_readback_mismatch")
        if not all(xfa_matches.values()):
            raise ValueError("xfa_datasets_readback_mismatch")
        result["technical_subset_readback_verified"] = True
        result["status"] = "technical_subset_passed_not_adobe_validated"
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        result["blocker"] = (str(exc) if isinstance(exc, ValueError)
                             else type(exc).__name__)
    except Exception as exc:
        # Never include exception text that might contain private form fields.
        result["blocker"] = "unexpected_" + type(exc).__name__
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-input-sha256", required=True)
    parser.add_argument("--official-imm5476", action="store_true")
    args = parser.parse_args()
    try:
        original = args.original.read_bytes()
        output = args.output.read_bytes()
        result = verify(original, output,
                        expected_input_hash=args.expected_input_sha256,
                        official=args.official_imm5476)
    except OSError:
        result = {
            "schema_version": "xfa-independent-readback-v1",
            "status": "blocked", "blocker": "missing_or_unreadable_local_pdf",
            "technical_subset_readback_verified": False,
            "adobe_reader_tested": False, "ircc_form_validated": False,
            "government_submission_supported": False,
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "technical_subset_passed_not_adobe_validated" else 2


if __name__ == "__main__":
    raise SystemExit(main())
