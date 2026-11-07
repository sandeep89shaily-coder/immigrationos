"""Authentic IMM 5476 (11-2025) proof of concept, SYNTHETIC DATA ONLY.

Tested against the uploaded official PDF (SHA-256 pinned below). This form
contains AES-encrypted PDF objects, an XFA packet array, AcroForm widgets and
Adobe usage rights (/UR3). Ordinary pypdf rewriting broke the XFA stream.
PyMuPDF incremental updates changed BOTH the XFA datasets and visible
AcroForm widgets without changing the original PDF byte prefix.

This experiment is NOT approved for real applicants, signing, government
submission or any claim that Adobe Reader has validated the result.
"""
from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET

from pypdf import PdfReader

FORM_CODE = "IMM5476"
REVISION = "11-2025"
SOURCE_SHA256 = "aca5c476b93d1c496b1afbc2cfe843499e852e31dcf0c192153bd01f8d6c56c4"
MAX_BYTES = 12 * 1024 * 1024
PAGE_COUNT = 4
SYNTHETIC_VALUES = {
    "applicant_family": "Sharma",
    "applicant_given": "Aarav",
    "applicant_dob": "2001-06-09",
    "applicant_email": "aarav@example.test",
    "application_type": "Study permit",
    "representative_family": "Kapoor",
    "representative_given": "Anita",
    "representative_firm": "Fictional Maple Immigration",
    "representative_city": "Toronto",
    "representative_province": "Ontario",
    "representative_country": "Canada",
    "representative_email": "anita@example.test",
}


class IMM5476ExperimentBlocked(ValueError):
    pass


@dataclass(frozen=True)
class FieldBinding:
    # Complete Acrobat field name, as actually recorded in the uploaded PDF.
    acroform_name: str
    # XML child path below xfa:data; explicit positional index disambiguates
    # repeated XFA elements such as the three 'office' fields.
    xfa_path: tuple[tuple[str, int], ...]


def _path(*segments):
    return tuple((name, index) for name, index in segments)


_BASE = "IMM_5476[0].Page1[0]."
_A = _BASE + "SectionA[0]."
_B = _BASE + "SectionB[0]."
_Q7 = _B + "question7[0]."
_FIELDS = {
    "applicant_family": FieldBinding(_A + "familyName[0]", _path(
        ("IMM_5476", 0), ("Page1", 0), ("SectionA", 0),
        ("familyName", 0), ("body", 0), ("p", 0), ("span", 0))),
    "applicant_given": FieldBinding(_A + "givenName[0]", _path(
        ("IMM_5476", 0), ("Page1", 0), ("SectionA", 0), ("givenName", 0))),
    "applicant_dob": FieldBinding(_A + "DOB[0]", _path(
        ("IMM_5476", 0), ("Page1", 0), ("SectionA", 0), ("DOB", 0))),
    "applicant_email": FieldBinding(_A + "office[0]", _path(
        ("IMM_5476", 0), ("Page1", 0), ("SectionA", 0), ("office", 0))),
    "application_type": FieldBinding(_A + "office[2]", _path(
        ("IMM_5476", 0), ("Page1", 0), ("SectionA", 0), ("office", 2))),
    "representative_family": FieldBinding(_B + "familyName[0]", _path(
        ("IMM_5476", 0), ("Page1", 0), ("SectionB", 0),
        ("familyName", 0), ("body", 0), ("p", 0), ("span", 0))),
    "representative_given": FieldBinding(_B + "givenName[0]", _path(
        ("IMM_5476", 0), ("Page1", 0), ("SectionB", 0), ("givenName", 0))),
    "representative_firm": FieldBinding(_Q7 + "organization[0]", _path(
        ("IMM_5476", 0), ("Page1", 0), ("SectionB", 0), ("question7", 0),
        ("organization", 0))),
    "representative_city": FieldBinding(_Q7 + "city[0]", _path(
        ("IMM_5476", 0), ("Page1", 0), ("SectionB", 0), ("question7", 0),
        ("city", 0))),
    "representative_province": FieldBinding(_Q7 + "province[0]", _path(
        ("IMM_5476", 0), ("Page1", 0), ("SectionB", 0), ("question7", 0),
        ("province", 0))),
    "representative_country": FieldBinding(_Q7 + "country[0]", _path(
        ("IMM_5476", 0), ("Page1", 0), ("SectionB", 0), ("question7", 0),
        ("country", 0))),
    "representative_email": FieldBinding(_Q7 + "email[0]", _path(
        ("IMM_5476", 0), ("Page1", 0), ("SectionB", 0), ("question7", 0),
        ("email", 0))),
}
assert set(_FIELDS) == set(SYNTHETIC_VALUES)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xfa_leaf(root: ET.Element, path: tuple[tuple[str, int], ...]) -> ET.Element:
    data = [e for e in root if _local(e.tag) == "data"]
    if len(data) != 1:
        raise IMM5476ExperimentBlocked("Expected exactly one XFA data root")
    current = data[0]
    for name, index in path:
        matches = [e for e in current if _local(e.tag) == name]
        if index >= len(matches):
            raise IMM5476ExperimentBlocked("Approved XFA binding is missing or changed")
        current = matches[index]
    if len(current):
        raise IMM5476ExperimentBlocked("XFA mapping unexpectedly targets a parent element")
    return current


def _find_xfa_packet(reader: PdfReader, packet: str):
    root = reader.trailer["/Root"]
    acro = root.get("/AcroForm")
    if not acro:
        raise IMM5476ExperimentBlocked("No form dictionary")
    xfa = acro.get_object().get("/XFA")
    if not xfa:
        raise IMM5476ExperimentBlocked("No XFA packets")
    packets = xfa.get_object()
    if not isinstance(packets, list) or len(packets) % 2:
        raise IMM5476ExperimentBlocked("Unexpected XFA representation")
    found = [packets[i + 1] for i in range(0, len(packets), 2) if str(packets[i]) == packet]
    if len(found) != 1:
        raise IMM5476ExperimentBlocked("Missing or duplicate XFA packet: " + packet)
    return found[0]


def _parse_xml(blob: bytes) -> ET.Element:
    if len(blob) > 3 * 1024 * 1024 or re.search(rb"<!\s*(?:ENTITY|DOCTYPE)\b", blob, re.I):
        raise IMM5476ExperimentBlocked("XFA XML exceeds limits or has unsafe declarations")
    try:
        return ET.fromstring(blob)
    except ET.ParseError as exc:
        raise IMM5476ExperimentBlocked("Invalid XFA XML") from exc


def _validate_original(raw: bytes) -> tuple[int, bytes, ET.Element]:
    if len(raw) > MAX_BYTES or sha256(raw).hexdigest() != SOURCE_SHA256:
        raise IMM5476ExperimentBlocked("Form does not match the independently inspected official revision")
    reader = PdfReader(__import__("io").BytesIO(raw), strict=True)
    if len(reader.pages) != PAGE_COUNT or "/UR3" not in reader.trailer["/Root"].get("/Perms", {}).get_object():
        raise IMM5476ExperimentBlocked("Form pages or Reader usage-rights baseline changed")
    fields = reader.get_fields() or {}
    for binding in _FIELDS.values():
        if binding.acroform_name not in fields or str(fields[binding.acroform_name].get("/FT")) != "/Tx":
            raise IMM5476ExperimentBlocked("PDF field map differs from observed baseline")
        if fields[binding.acroform_name].get("/V") not in (None, ""):
            raise IMM5476ExperimentBlocked("Template is not blank")
    template = _find_xfa_packet(reader, "template").get_object().get_data()
    packet = _find_xfa_packet(reader, "datasets")
    xml = packet.get_object().get_data()
    root = _parse_xml(xml)
    for binding in _FIELDS.values():
        _xfa_leaf(root, binding.xfa_path)
    return packet.idnum, template, root


def _verify_result(raw: bytes, output: bytes, original_template: bytes):
    from io import BytesIO
    if not output.startswith(raw):
        raise IMM5476ExperimentBlocked("Incremental output changed original PDF bytes")
    saved = PdfReader(BytesIO(output), strict=True)
    if len(saved.pages) != PAGE_COUNT:
        raise IMM5476ExperimentBlocked("Page count changed")
    if "/UR3" not in saved.trailer["/Root"].get("/Perms", {}).get_object():
        raise IMM5476ExperimentBlocked("Reader usage-rights marker lost")
    fields = saved.get_fields() or {}
    xfa_root = _parse_xml(_find_xfa_packet(saved, "datasets").get_object().get_data())
    if _find_xfa_packet(saved, "template").get_object().get_data() != original_template:
        raise IMM5476ExperimentBlocked("Original XFA template stream was modified")
    for key, binding in _FIELDS.items():
        if str(fields[binding.acroform_name].get("/V", "")) != SYNTHETIC_VALUES[key]:
            raise IMM5476ExperimentBlocked("AcroForm round-trip mismatch for " + key)
        if _xfa_leaf(xfa_root, binding.xfa_path).text != SYNTHETIC_VALUES[key]:
            raise IMM5476ExperimentBlocked("XFA round-trip mismatch for " + key)


def generate_fictional_imm5476(blank_pdf: Path, output_pdf: Path) -> dict:
    """Create an UNSIGNED, NOT ADOBE-VALIDATED demonstration PDF.

    Accepts only one exact SHA-256-pinned blank template and fixed fictional
    values. User/client inputs deliberately cannot enter this experimental path.
    """
    import fitz

    blank_pdf = Path(blank_pdf).resolve()
    output_pdf = Path(output_pdf).resolve()
    if blank_pdf == output_pdf:
        raise IMM5476ExperimentBlocked("Never overwrite the official blank")
    if output_pdf.exists():
        raise IMM5476ExperimentBlocked("Refusing to overwrite existing output")
    raw = blank_pdf.read_bytes()
    dataset_xref, original_template, root = _validate_original(raw)
    for key, binding in _FIELDS.items():
        _xfa_leaf(root, binding.xfa_path).text = SYNTHETIC_VALUES[key]
    patched_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    if len(patched_xml) > 3 * 1024 * 1024:
        raise IMM5476ExperimentBlocked("Patched XFA data exceeds size limits")
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    fd, scratch_name = tempfile.mkstemp(prefix="imm5476-synthetic-", suffix=".pdf",
                                        dir=output_pdf.parent)
    os.close(fd)
    scratch = Path(scratch_name)
    try:
        shutil.copyfile(blank_pdf, scratch)
        with fitz.open(scratch) as pdf:
            if pdf.page_count != PAGE_COUNT or not pdf.can_save_incrementally():
                raise IMM5476ExperimentBlocked("Incremental update unsupported")
            pdf.update_stream(dataset_xref, patched_xml)
            completed = set()
            for page in pdf:
                for widget in page.widgets() or []:
                    for key, binding in _FIELDS.items():
                        if widget.field_name == binding.acroform_name:
                            if key in completed:
                                raise IMM5476ExperimentBlocked("Duplicate form widget")
                            widget.field_value = SYNTHETIC_VALUES[key]
                            widget.update()
                            completed.add(key)
            if completed != set(_FIELDS):
                raise IMM5476ExperimentBlocked("Some official PDF widgets were not found")
            pdf.saveIncr()
        result = scratch.read_bytes()
        _verify_result(raw, result, original_template)
        os.replace(scratch, output_pdf)
        return {
            "form_code": FORM_CODE, "source_revision": REVISION,
            "source_sha256": SOURCE_SHA256,
            "output_sha256": sha256(result).hexdigest(),
            "fictional_fields_verified": len(_FIELDS),
            "original_bytes_preserved_by_incremental_save": True,
            "xfa_template_stream_preserved": True,
            "pdf_field_roundtrip_verified": True,
            "xfa_field_roundtrip_verified": True,
            "adobe_reader_validation_verified": False,
            "signature_validation_verified": False,
            "ready_for_submission": False,
            "warning": "Synthetic partial prefill only. Representative classification, authorization, signatures and Adobe Reader review remain outstanding.",
        }
    finally:
        scratch.unlink(missing_ok=True)
