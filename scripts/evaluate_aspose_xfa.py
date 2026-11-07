"""Isolated third-party XFA compatibility trial; never used in ImmigrationOS production.

Target: original blank IRCC IMM5476 (11-2025) with known SHA-256.
Output: fixed fictional data only, explicitly NOT ready for IRCC submission.

Run with an *optional* commercial Aspose.PDF Python/.NET installation:
    pip install 'aspose-pdf==26.9.0'
    python -m scripts.evaluate_aspose_xfa --input /path/to/imm5476e.pdf \\
        --output /tmp/aspose-imm5476-UNVALIDATED.pdf --report /tmp/aspose-result.json

This is deliberately an isolated SDK evaluation, not a fallback to pypdf,
PyMuPDF, XFA flattening, AcroForm-only filling or barcode fabrication.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from io import FileIO
import tempfile
import xml.etree.ElementTree as ET
import sys
import traceback

from app.imm5476_official_poc import (
    _FIELDS, _find_xfa_packet, _parse_xml, _xfa_leaf,
    SOURCE_SHA256, SYNTHETIC_VALUES,
)

# Keep trial at or below four mapped fields; unlicensed Aspose evaluations
# may restrict collection traversal and watermark generated output.
TARGET_KEYS = (
    "applicant_family", "applicant_given",
    "representative_family", "representative_given",
)
MAX_SOURCE_BYTES = 12 * 1024 * 1024


class AsposeTrialBlocked(RuntimeError):
    pass


def resolve_field_names(inventory, requested=TARGET_KEYS):
    """Select only unambiguous, observed names. Never guess unknown XFA paths."""
    result = {}
    present = [str(x) for x in inventory]
    for key in requested:
        expected = _FIELDS[key].acroform_name
        hits = [name for name in present
                if name == expected or name.endswith("." + expected)]
        if len(hits) == 1:
            result[key] = hits[0]
        elif len(hits) > 1:
            raise AsposeTrialBlocked("Ambiguous XFA field inventory: " + key)
    return result


def inspect_output(output: Path, mapped: dict) -> dict:
    """Independent structural readback. Does not certify Adobe XFA behavior."""
    from pypdf import PdfReader
    try:
        reader = PdfReader(str(output), strict=True)
        if len(reader.pages) != 4:
            return {"readback": "wrong_page_count", "pages": len(reader.pages)}
        acro = reader.get_fields() or {}
        root = _parse_xml(_find_xfa_packet(reader, "datasets").get_object().get_data())
        verification = {}
        for key in mapped:
            binding = _FIELDS[key]
            xfa_text = _xfa_leaf(root, binding.xfa_path).text
            acro_text = str(acro.get(binding.acroform_name, {}).get("/V", ""))
            verification[key] = {
                "xfa_matches": xfa_text == SYNTHETIC_VALUES[key],
                "acroform_matches": acro_text == SYNTHETIC_VALUES[key],
            }
        perm = reader.trailer["/Root"].get("/Perms")
        return {
            "readback": "completed",
            "pages": len(reader.pages),
            "xfa_and_acroform": verification,
            "ur3_marker_present": bool(perm and "/UR3" in perm.get_object()),
            "all_xfa_values_match": bool(verification) and all(
                status["xfa_matches"] for status in verification.values()),
        }
    except Exception as exc:
        return {"readback": "error", "error_type": type(exc).__name__}


def run_trial(input_path: Path, output_path: Path) -> dict:
    """SDK does all PDF writing; no fallback if its XFA support fails."""
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    if input_path == output_path or output_path.exists():
        raise AsposeTrialBlocked("Must use a new, separate output path")
    blob = input_path.read_bytes()
    if len(blob) > MAX_SOURCE_BYTES or sha256(blob).hexdigest() != SOURCE_SHA256:
        raise AsposeTrialBlocked("Official PDF SHA-256 mismatch; refusing to touch template")
    import aspose.pdf as ap  # optional commercial dependency; only in isolated CLI

    report = {
        "engine": "Aspose.PDF for Python via .NET (evaluation)",
        "form_code": "IMM5476",
        "template_revision": "11-2025",
        "source_sha256": SOURCE_SHA256,
        "test_data": "fictional_only",
        "official_validation": False,
        "adobe_reader_tested": False,
        "ready_for_submission": False,
    }
    # Document.form.xfa supports field enumeration but does not expose the
    # C# XFA indexer setter in Python. Aspose's documented Python entry point
    # for XFA data injection is facades.Form.set_xfa_data().
    import aspose.pdf.facades as pdf_facades
    from pypdf import PdfReader
    with ap.Document(str(input_path)) as document:
        names = [str(name) for name in document.form.xfa.field_names]
    report["xfa_field_inventory_count"] = len(names)
    report["engine_can_enumerate_xfa"] = bool(names)
    selected = resolve_field_names(names)
    report["mapped_keys"] = sorted(selected)
    report["requested_keys"] = list(TARGET_KEYS)
    report["write_api"] = "facades.Form.set_xfa_data"
    if not selected:
        report["status"] = "no_matching_xfa_fields_visible_in_trial"
        report["note"] = "Evaluation collection limit or XFA naming differs from canonical PDF fields"
        return report
    source_reader = PdfReader(str(input_path), strict=True)
    dataset_bytes = _find_xfa_packet(source_reader, "datasets").get_object().get_data()
    root = _parse_xml(dataset_bytes)
    for key in selected:
        _xfa_leaf(root, _FIELDS[key].xfa_path).text = SYNTHETIC_VALUES[key]
    prepared_xml = ET.tostring(root, encoding="utf-8", xml_declaration=False)
    if len(prepared_xml) > 3 * 1024 * 1024:
        raise AsposeTrialBlocked("XFA datasets too large")
    with tempfile.TemporaryDirectory(prefix="imm5476-aspose-test-") as tempdir:
        xml_path = Path(tempdir) / "fictional-xfa-datasets.xml"
        xml_path.write_bytes(prepared_xml)
        facade = pdf_facades.Form()
        facade.bind_pdf(str(input_path))
        with FileIO(str(xml_path), "r") as xml_stream:
            facade.set_xfa_data(xml_stream)
        facade.save(str(output_path))

    if not output_path.is_file() or not output_path.read_bytes().startswith(b"%PDF-"):
        report["status"] = "vendor_failed_to_save_pdf"
        return report
    report["output_sha256"] = sha256(output_path.read_bytes()).hexdigest()
    report.update(inspect_output(output_path, selected))
    report["status"] = (
        "xfa_values_written_and_read_back"
        if report.get("all_xfa_values_match") else "xfa_values_unverified_or_changed"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "engine": "aspose_pdf",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "status": "not_tested",
        "official_validation": False,
        "adobe_reader_tested": False,
        "ready_for_submission": False,
    }
    try:
        result.update(run_trial(args.input, args.output))
        code = 0 if result["status"] == "xfa_values_written_and_read_back" else 2
    except (AsposeTrialBlocked, ImportError, OSError, AttributeError, TypeError, ValueError) as exc:
        result.update({"status": "blocked_or_failed",
                       "error_type": type(exc).__name__,
                       "error_description": str(exc)[:350]})
        code = 2
    except Exception as exc:
        # Keep vendor crashes and opaque errors visible without dumping PDF contents.
        result.update({"status": "vendor_exception",
                       "error_type": type(exc).__name__,
                       "error_description": str(exc)[:350]})
        code = 2
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
